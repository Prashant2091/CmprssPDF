from __future__ import annotations

import inspect
import re
from collections import defaultdict
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Iterable
from zipfile import ZipFile, ZIP_DEFLATED

import streamlit as st
from PyPDF2 import PdfReader, PdfWriter
from PyPDF2.errors import PdfReadError


# =========================
# Data model
# =========================
@dataclass
class CompressionResult:
    filename: str
    original_size: int
    attempted_size: int          # best attempt bytes size (may be >= original)
    output_size: int             # delivered bytes size (may be original if kept)
    data: bytes
    used_original: bool = False
    backend: str = "auto"
    note: str = ""
    analysis: dict | None = None


# =========================
# Helpers
# =========================
def format_size(num_bytes: int) -> str:
    if num_bytes < 1024:
        return f"{num_bytes} B"
    if num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.2f} KB"
    return f"{num_bytes / 1024 / 1024:.2f} MB"


def build_output_name(filename: str, suffix: str) -> str:
    p = Path(filename)
    if not p.suffix:
        return f"{filename}{suffix}.pdf"
    return f"{p.stem}{suffix}{p.suffix}"


def dedupe_names(results: Iterable[CompressionResult]) -> list[CompressionResult]:
    seen: dict[str, int] = {}
    out: list[CompressionResult] = []
    for r in results:
        c = seen.get(r.filename, 0)
        if c == 0:
            seen[r.filename] = 1
            out.append(r)
            continue
        stem = Path(r.filename).stem
        suff = Path(r.filename).suffix
        new_name = f"{stem}-{c + 1}{suff}"
        seen[r.filename] = c + 1
        out.append(
            CompressionResult(
                filename=new_name,
                original_size=r.original_size,
                attempted_size=r.attempted_size,
                output_size=r.output_size,
                data=r.data,
                used_original=r.used_original,
                backend=r.backend,
                note=r.note,
                analysis=r.analysis,
            )
        )
    return out


def build_zip(results: Iterable[CompressionResult]) -> bytes:
    buf = BytesIO()
    with ZipFile(buf, "w", compression=ZIP_DEFLATED, compresslevel=9) as zf:
        for r in results:
            zf.writestr(r.filename, r.data)
    buf.seek(0)
    return buf.getvalue()


def _supports_kw(fn, kw: str) -> bool:
    try:
        sig = inspect.signature(fn)
    except Exception:
        return False
    if kw in sig.parameters:
        return True
    return any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())


# =========================
# PyPDF2 lossless fallback
# =========================
def _compress_with_pypdf2_lossless(input_bytes: bytes, *, password: str | None, remove_metadata: bool) -> bytes:
    try:
        reader = PdfReader(BytesIO(input_bytes))
    except PdfReadError as exc:
        raise ValueError("The file could not be read as a PDF.") from exc

    if reader.is_encrypted:
        if not password:
            raise ValueError("This PDF is password-protected. Provide a password to continue.")
        if reader.decrypt(password) == 0:
            raise ValueError("Unable to decrypt the PDF with the provided password.")

    writer = PdfWriter()

    if hasattr(writer, "clone_document_from_reader"):
        writer.clone_document_from_reader(reader)
        for page in writer.pages:
            try:
                page.compress_content_streams()
            except Exception:
                pass
    else:
        for page in reader.pages:
            try:
                page.compress_content_streams()
            except Exception:
                pass
            writer.add_page(page)

    if not remove_metadata:
        try:
            if reader.metadata:
                md = {k: str(v) for k, v in reader.metadata.items() if v is not None}
                if md:
                    writer.add_metadata(md)
        except Exception:
            pass

    out = BytesIO()
    writer.write(out)
    out.seek(0)
    return out.getvalue()


# =========================
# Pikepdf helpers (best)
# =========================
def _safe_pikepdf_save(pdf, out: BytesIO, kwargs: dict) -> None:
    kwargs = dict(kwargs)
    while True:
        try:
            pdf.save(out, **kwargs)
            return
        except TypeError as e:
            msg = str(e)
            m = re.search(r"unexpected keyword argument '(\w+)'", msg)
            if not m:
                raise
            kwargs.pop(m.group(1), None)
            if not kwargs:
                raise


def _pikepdf_open_or_raise(input_bytes: bytes, password: str | None):
    """
    CRITICAL FIX: pikepdf requires password as str. Never pass None.
    """
    import pikepdf

    try:
        return pikepdf.open(BytesIO(input_bytes), password=password or "")
    except Exception as exc:
        PasswordError = getattr(pikepdf, "PasswordError", None)
        PdfError = getattr(pikepdf, "PdfError", None)

        if PasswordError and isinstance(exc, PasswordError):
            if not password:
                raise ValueError("This PDF is password-protected. Provide a password to continue.")
            raise ValueError("Unable to decrypt the PDF with the provided password.")

        if PdfError and isinstance(exc, PdfError):
            raise ValueError("The file could not be read as a PDF.")
        raise


def _pikepdf_remove_metadata(pdf) -> None:
    try:
        if "/Metadata" in pdf.Root:
            del pdf.Root["/Metadata"]
    except Exception:
        pass
    try:
        pdf.docinfo.clear()
    except Exception:
        pass


def _pikepdf_copy_metadata(src_pdf, dst_pdf) -> None:
    try:
        try:
            dst_pdf.docinfo.clear()
            for k, v in src_pdf.docinfo.items():
                dst_pdf.docinfo[k] = v
        except Exception:
            pass

        try:
            src_meta = src_pdf.open_metadata()
            with dst_pdf.open_metadata() as dst_meta:
                for k in list(dst_meta.keys()):
                    try:
                        del dst_meta[k]
                    except Exception:
                        pass
                for k in list(src_meta.keys()):
                    try:
                        dst_meta[k] = src_meta[k]
                    except Exception:
                        pass
        except Exception:
            pass
    except Exception:
        pass


def _pikepdf_save_bytes(pdf, kwargs: dict) -> bytes:
    out = BytesIO()
    _safe_pikepdf_save(pdf, out, kwargs)
    out.seek(0)
    return out.getvalue()


def _pikepdf_save_best(pdf, base_kwargs: dict, *, original_size: int | None, try_harder: bool) -> bytes:
    best = _pikepdf_save_bytes(pdf, base_kwargs)
    best_len = len(best)

    if not try_harder:
        return best

    if original_size is not None and best_len <= original_size:
        return best

    variants: list[dict] = []

    if "object_stream_mode" in base_kwargs:
        v = dict(base_kwargs)
        v.pop("object_stream_mode", None)
        variants.append(v)

    v = dict(base_kwargs)
    v["normalize_content"] = False
    variants.append(v)

    v = dict(base_kwargs)
    v["recompress_flate"] = False
    variants.append(v)

    if "compression_level" in base_kwargs:
        v = dict(base_kwargs)
        lvl = int(v.get("compression_level", 9))
        v["compression_level"] = 6 if lvl > 6 else max(1, lvl - 1)
        variants.append(v)

    for v in variants:
        try:
            b = _pikepdf_save_bytes(pdf, v)
            if len(b) < best_len:
                best = b
                best_len = len(b)
        except Exception:
            continue

    return best


def _stream_raw_size(stream) -> int | None:
    try:
        b = stream.read_raw_bytes()
        return len(b) if b is not None else None
    except Exception:
        try:
            b = stream.read_bytes()
            return len(b) if b is not None else None
        except Exception:
            return None


def _filter_list(xobj) -> list[str]:
    """
    Return PDF filter(s) as list of strings, e.g. ["DCTDecode"] or ["FlateDecode"].
    """
    try:
        f = xobj.get("/Filter", None)
        if f is None:
            return []
        if isinstance(f, list):
            return [str(i).strip("/") for i in f]
        return [str(f).strip("/")]
    except Exception:
        return []


# =========================
# Image scanning: recursive XObject traversal
# =========================
def _iter_image_xobjects(obj, *, visited: set[tuple[int, int]]):
    try:
        resources = obj.get("/Resources", None)
        if not resources:
            return
        xobjs = resources.get("/XObject", None)
        if not xobjs:
            return
    except Exception:
        return

    for name in list(xobjs.keys()):
        try:
            xo = xobjs[name]
            og = getattr(xo, "objgen", None)
            if og and og in visited:
                continue
            if og:
                visited.add(og)

            subtype = xo.get("/Subtype", None)
            if subtype == "/Image":
                yield (name, xo)
            elif subtype == "/Form":
                yield from _iter_image_xobjects(xo, visited=visited)
        except Exception:
            continue


def _page_inches(page) -> tuple[float, float] | None:
    try:
        mb = page.MediaBox
        w_pt = float(mb[2] - mb[0])
        h_pt = float(mb[3] - mb[1])
        if w_pt <= 0 or h_pt <= 0:
            return None
        return (w_pt / 72.0, h_pt / 72.0)
    except Exception:
        return None


# =========================
# PDF analysis (why compression is limited)
# =========================
def analyze_pdf_bytes(input_bytes: bytes, *, password: str | None) -> dict:
    """
    Lightweight “why size won’t drop much” detector.
    Does not decode images (fast), uses stream raw sizes.
    """
    info = {
        "pages": None,
        "image_count": 0,
        "image_raw_total": 0,
        "image_share_of_file": 0.0,
        "filters": {},
        "likely_scanned": False,
        "already_jpeg_heavy": False,
        "note": "",
    }
    try:
        import pikepdf
    except Exception:
        info["note"] = "pikepdf not installed → analysis unavailable."
        return info

    try:
        pdf = _pikepdf_open_or_raise(input_bytes, password)
    except Exception as exc:
        info["note"] = f"Analysis open failed: {exc}"
        return info

    filters = defaultdict(int)
    image_raw_total = 0
    image_count = 0

    visited: set[tuple[int, int]] = set()
    with pdf:
        info["pages"] = len(pdf.pages)
        for page in pdf.pages:
            for _, img in _iter_image_xobjects(page, visited=visited):
                image_count += 1
                rs = _stream_raw_size(img)
                if rs:
                    image_raw_total += rs
                fl = _filter_list(img)
                if not fl:
                    filters["(none)"] += 1
                else:
                    for f in fl:
                        filters[f] += 1

    info["image_count"] = image_count
    info["image_raw_total"] = image_raw_total
    if len(input_bytes) > 0:
        info["image_share_of_file"] = float(image_raw_total) / float(len(input_bytes))

    # Heuristics
    pages = info["pages"] or 0
    image_share = info["image_share_of_file"]
    dct = filters.get("DCTDecode", 0)
    total_imgs = max(1, image_count)

    info["already_jpeg_heavy"] = (dct / total_imgs) >= 0.7
    info["likely_scanned"] = (image_share >= 0.6) and (image_count >= max(1, pages))

    info["filters"] = dict(sorted(filters.items(), key=lambda kv: kv[1], reverse=True))
    return info


# =========================
# Mode 1: Lossless
# =========================
def compress_pdf_lossless(
    input_bytes: bytes,
    *,
    password: str | None,
    remove_metadata: bool,
    backend: str,
    compression_level: int,
    object_streams: bool,
    linearize: bool,
    try_harder: bool,
) -> tuple[bytes, str, str]:
    backend = backend.lower().strip()

    if backend in {"auto", "pikepdf"}:
        try:
            import pikepdf
            pdf = _pikepdf_open_or_raise(input_bytes, password)
            with pdf:
                if remove_metadata:
                    _pikepdf_remove_metadata(pdf)

                kwargs = {
                    "compress_streams": True,
                    "linearize": bool(linearize),
                    "normalize_content": True,
                    "recompress_flate": True,
                    "compression_level": int(max(1, min(9, compression_level))),
                }
                if object_streams and hasattr(pikepdf, "ObjectStreamMode"):
                    kwargs["object_stream_mode"] = pikepdf.ObjectStreamMode.generate

                out_bytes = _pikepdf_save_best(pdf, kwargs, original_size=len(input_bytes), try_harder=try_harder)
                return out_bytes, "pikepdf(qpdf) lossless", "Lossless rewrite + stream recompression."
        except ImportError:
            if backend == "pikepdf":
                raise ValueError("Backend 'pikepdf' selected but pikepdf is not installed.")
        except Exception:
            if backend == "pikepdf":
                raise

    out = _compress_with_pypdf2_lossless(input_bytes, password=password, remove_metadata=remove_metadata)
    return out, "PyPDF2 lossless", "Lossless content stream compression (limited)."


# =========================
# Mode 2: Scan/Turbo (JPEG)
# =========================
def compress_pdf_scan_turbo_once(
    input_bytes: bytes,
    *,
    password: str | None,
    remove_metadata: bool,
    target_dpi: int,
    jpeg_quality: int,
    grayscale: bool,
    min_megapixels: float,
    compression_level: int,
    object_streams: bool,
    linearize: bool,
    try_harder: bool,
) -> tuple[bytes, str, str]:
    try:
        import pikepdf
        from pikepdf import PdfImage, Name
        from PIL import Image
    except ImportError as exc:
        raise ValueError("Scan/Turbo requires pikepdf + pillow. Install: pip install pikepdf pillow") from exc

    Image.MAX_IMAGE_PIXELS = None
    pdf = _pikepdf_open_or_raise(input_bytes, password)

    images_total = 0
    images_optimized = 0
    images_skipped = 0
    min_pixels = int(max(0.0, min_megapixels) * 1_000_000)
    visited: set[tuple[int, int]] = set()

    with pdf:
        if remove_metadata:
            _pikepdf_remove_metadata(pdf)

        for page in pdf.pages:
            page_in = _page_inches(page)
            if page_in:
                pw_in, ph_in = page_in
                t_w = int(max(1, min(20000, round(pw_in * target_dpi))))
                t_h = int(max(1, min(20000, round(ph_in * target_dpi))))
            else:
                t_w = t_h = None

            for _, rawimg in _iter_image_xobjects(page, visited=visited):
                images_total += 1

                # Skip masks/transparency
                try:
                    if rawimg.get("/ImageMask", False) or ("/SMask" in rawimg) or ("/Mask" in rawimg):
                        images_skipped += 1
                        continue
                except Exception:
                    images_skipped += 1
                    continue

                try:
                    w = int(rawimg.get("/Width", 0))
                    h = int(rawimg.get("/Height", 0))
                    if w <= 0 or h <= 0 or (w * h) < min_pixels:
                        images_skipped += 1
                        continue
                except Exception:
                    images_skipped += 1
                    continue

                old_raw = _stream_raw_size(rawimg)

                try:
                    pim = PdfImage(rawimg).as_pil_image()
                except Exception:
                    images_skipped += 1
                    continue

                try:
                    if grayscale:
                        if pim.mode != "L":
                            pim = pim.convert("L")
                    else:
                        if pim.mode != "RGB":
                            pim = pim.convert("RGB")
                except Exception:
                    images_skipped += 1
                    continue

                # Downsample (never upscale)
                try:
                    if t_w and t_h and (pim.width > t_w or pim.height > t_h):
                        scale = min(t_w / pim.width, t_h / pim.height)
                        nw = max(1, int(pim.width * scale))
                        nh = max(1, int(pim.height * scale))
                        pim = pim.resize((nw, nh), Image.Resampling.LANCZOS)
                except Exception:
                    pass

                try:
                    buf = BytesIO()
                    pim.save(
                        buf,
                        format="JPEG",
                        quality=int(max(40, min(95, jpeg_quality))),
                        optimize=True,
                        progressive=True,
                    )
                    jpeg_bytes = buf.getvalue()
                except Exception:
                    images_skipped += 1
                    continue

                # Skip if replacement would be bigger than original encoded image stream
                if old_raw is not None and len(jpeg_bytes) >= old_raw:
                    images_skipped += 1
                    continue

                try:
                    rawimg.write(jpeg_bytes, filter=Name("/DCTDecode"))
                    rawimg.Width, rawimg.Height = pim.width, pim.height
                    rawimg.BitsPerComponent = 8
                    rawimg.ColorSpace = Name("/DeviceGray") if grayscale else Name("/DeviceRGB")
                    try:
                        if "/DecodeParms" in rawimg:
                            del rawimg["/DecodeParms"]
                    except Exception:
                        pass
                    images_optimized += 1
                except Exception:
                    images_skipped += 1
                    continue

        kwargs = {
            "compress_streams": True,
            "linearize": bool(linearize),
            "normalize_content": True,
            "recompress_flate": True,
            "compression_level": int(max(1, min(9, compression_level))),
        }
        if object_streams and hasattr(pikepdf, "ObjectStreamMode"):
            kwargs["object_stream_mode"] = pikepdf.ObjectStreamMode.generate

        out_bytes = _pikepdf_save_best(pdf, kwargs, original_size=len(input_bytes), try_harder=try_harder)
        note = f"Images total: {images_total}, optimized: {images_optimized}, skipped: {images_skipped}"
        return out_bytes, "pikepdf(qpdf) scan/turbo", note


def compress_pdf_scan_turbo_best(
    input_bytes: bytes,
    *,
    password: str | None,
    remove_metadata: bool,
    base_target_dpi: int,
    base_quality: int,
    base_grayscale: bool,
    min_megapixels: float,
    compression_level: int,
    object_streams: bool,
    linearize: bool,
    try_harder: bool,
    auto_optimize: bool,
    search_depth: int,
    target_reduction_pct: float | None,
    stop_when_target_met: bool,
) -> tuple[bytes, str, str]:
    """
    If auto_optimize: tries multiple DPI/quality combos (gentle->aggressive) and picks best.
    """
    original_size = len(input_bytes)
    target_size = None
    if target_reduction_pct is not None:
        target_size = int(original_size * (1.0 - max(0.0, min(0.95, target_reduction_pct / 100.0))))

    # Ordered from minimal visual change → more aggressive
    attempts: list[tuple[int, int, bool]] = [(base_target_dpi, base_quality, base_grayscale)]

    if auto_optimize:
        # DPI steps (downsampling is the biggest lever for scans)
        for d in (base_target_dpi - 30, base_target_dpi - 60, base_target_dpi - 90, base_target_dpi - 120):
            if d >= 110:
                attempts.append((d, base_quality, base_grayscale))

        # Quality steps (secondary lever)
        for q in (base_quality - 5, base_quality - 10, base_quality - 15):
            if q >= 55:
                attempts.append((base_target_dpi, q, base_grayscale))

        # Combined
        if base_target_dpi - 60 >= 110 and base_quality - 10 >= 55:
            attempts.append((base_target_dpi - 60, base_quality - 10, base_grayscale))
        if base_target_dpi - 90 >= 110 and base_quality - 15 >= 55:
            attempts.append((base_target_dpi - 90, base_quality - 15, base_grayscale))

        # Grayscale variants (can be huge on color scans)
        if not base_grayscale:
            attempts.append((base_target_dpi, base_quality, True))
            if base_target_dpi - 60 >= 110:
                attempts.append((base_target_dpi - 60, base_quality, True))
            if base_target_dpi - 90 >= 110 and base_quality - 10 >= 55:
                attempts.append((base_target_dpi - 90, base_quality - 10, True))

        # Limit
        attempts = attempts[: max(1, int(search_depth))]

    best_bytes = None
    best_backend = ""
    best_note = ""
    best_params = None

    for (dpi, q, gs) in attempts:
        b, backend, note = compress_pdf_scan_turbo_once(
            input_bytes,
            password=password,
            remove_metadata=remove_metadata,
            target_dpi=int(dpi),
            jpeg_quality=int(q),
            grayscale=bool(gs),
            min_megapixels=min_megapixels,
            compression_level=compression_level,
            object_streams=object_streams,
            linearize=linearize,
            try_harder=try_harder,
        )

        if best_bytes is None or len(b) < len(best_bytes):
            best_bytes = b
            best_backend = backend
            best_note = note
            best_params = (dpi, q, gs)

        if stop_when_target_met and target_size is not None and len(b) <= target_size:
            # Stop early as soon as we meet target (this preserves quality by avoiding more aggressive attempts)
            best_bytes = b
            best_backend = backend
            best_note = note
            best_params = (dpi, q, gs)
            break

    assert best_bytes is not None
    ptxt = f"Best params: DPI={best_params[0]}, Q={best_params[1]}, grayscale={best_params[2]}"
    return best_bytes, best_backend, f"{best_note} | {ptxt}"


# =========================
# Mode 3: Ultra B/W (internal CCITT + OCRmyPDF optimize-only)
# =========================
def _bitrev_table() -> bytes:
    return bytes(int(f"{i:08b}"[::-1], 2) for i in range(256))


TIFF_BITREV = _bitrev_table()


class _temp_attr:
    def __init__(self, obj, field: str, value):
        self.obj = obj
        self.field = field
        self.value = value
        self.exists = False
        self.old_value = None

    def __enter__(self):
        if hasattr(self.obj, self.field):
            self.exists = True
            self.old_value = getattr(self.obj, self.field)
        setattr(self.obj, self.field, self.value)

    def __exit__(self, exctype, excinst, exctb):
        if self.exists:
            setattr(self.obj, self.field, self.old_value)
        else:
            delattr(self.obj, self.field)


def _ccitt_payload_location_from_pil(img):
    from PIL import TiffImagePlugin
    strip_offsets = img.tag_v2[TiffImagePlugin.STRIPOFFSETS]
    strip_bytes = img.tag_v2[TiffImagePlugin.STRIPBYTECOUNTS]
    if len(strip_offsets) != 1 or len(strip_bytes) != 1:
        raise NotImplementedError("Multiple strips not supported for PDF CCITT payload.")
    (offset,), (length,) = strip_offsets, strip_bytes
    return int(offset), int(length)


def _otsu_threshold_from_hist(hist: list[int]) -> int:
    total = sum(hist)
    if total <= 0:
        return 128
    sum_total = sum(i * hist[i] for i in range(256))
    sum_b = 0
    w_b = 0
    max_var = -1.0
    threshold = 128
    for t in range(256):
        w_b += hist[t]
        if w_b == 0:
            continue
        w_f = total - w_b
        if w_f == 0:
            break
        sum_b += t * hist[t]
        m_b = sum_b / w_b
        m_f = (sum_total - sum_b) / w_f
        var_between = w_b * w_f * (m_b - m_f) ** 2
        if var_between > max_var:
            max_var = var_between
            threshold = t
    return int(threshold)


def _is_nearly_bilevel(pil_img, *, tol: int = 12, ratio: float = 0.985) -> bool:
    try:
        g = pil_img.convert("L")
        max_side = 512
        if max(g.size) > max_side:
            scale = max_side / max(g.size)
            g = g.resize((max(1, int(g.width * scale)), max(1, int(g.height * scale))))
        hist = g.histogram()
        total = sum(hist)
        if total <= 0:
            return False
        near_black = sum(hist[: max(1, tol)])
        near_white = sum(hist[256 - max(1, tol) :])
        return (near_black + near_white) / total >= ratio
    except Exception:
        return False


def _transcode_monochrome_to_ccitt_g4(pil_bw_1bit):
    from PIL import Image, TiffImagePlugin, features as PIL_features

    if not PIL_features.check("libtiff"):
        raise RuntimeError("Pillow is not compiled with libtiff; cannot encode Group4 CCITT.")

    newimgio = BytesIO()
    img2 = Image.frombytes(pil_bw_1bit.mode, pil_bw_1bit.size, pil_bw_1bit.tobytes())
    tmp_strip_size = (pil_bw_1bit.size[0] + 7) // 8 * pil_bw_1bit.size[1]

    if hasattr(TiffImagePlugin, "STRIP_SIZE"):
        with _temp_attr(TiffImagePlugin, "STRIP_SIZE", tmp_strip_size):
            img2.save(newimgio, format="TIFF", compression="group4")
    else:
        pillow__getitem__ = TiffImagePlugin.ImageFileDirectory_v2.__getitem__

        def __getitem__(self, tag: int):
            overrides = {
                TiffImagePlugin.ROWSPERSTRIP: pil_bw_1bit.size[1],
                TiffImagePlugin.STRIPBYTECOUNTS: [tmp_strip_size],
                TiffImagePlugin.STRIPOFFSETS: [0],
            }
            return overrides.get(tag, pillow__getitem__(self, tag))

        with _temp_attr(TiffImagePlugin.ImageFileDirectory_v2, "__getitem__", __getitem__):
            img2.save(newimgio, format="TIFF", compression="group4")

    newimgio.seek(0)
    tiff_img = Image.open(newimgio)

    photo = tiff_img.tag_v2[TiffImagePlugin.PHOTOMETRIC_INTERPRETATION]
    inverted = (photo == 0)

    offset, length = _ccitt_payload_location_from_pil(tiff_img)
    newimgio.seek(offset)
    payload = newimgio.read(length)

    fillorder = tiff_img.tag_v2.get(TiffImagePlugin.FILLORDER)
    if fillorder == 2:
        payload = bytes(TIFF_BITREV[b] for b in payload)

    return payload, inverted


def compress_ultra_bw_internal_once(
    input_bytes: bytes,
    *,
    password: str | None,
    remove_metadata: bool,
    target_dpi: int,
    min_megapixels: float,
    only_if_nearly_bilevel: bool,
    threshold_mode: str,
    manual_threshold: int,
    fallback_jpeg_quality: int,
    compression_level: int,
    object_streams: bool,
    linearize: bool,
    try_harder: bool,
) -> tuple[bytes, str, str]:
    try:
        import pikepdf
        from pikepdf import PdfImage, Name, Dictionary
        from PIL import Image
    except ImportError as exc:
        raise ValueError("Ultra B/W internal CCITT requires pikepdf + pillow.") from exc

    Image.MAX_IMAGE_PIXELS = None
    pdf = _pikepdf_open_or_raise(input_bytes, password)

    images_total = 0
    images_ccitt = 0
    images_fallback_jpeg = 0
    images_skipped = 0

    min_pixels = int(max(0.0, min_megapixels) * 1_000_000)
    visited: set[tuple[int, int]] = set()

    with pdf:
        if remove_metadata:
            _pikepdf_remove_metadata(pdf)

        for page in pdf.pages:
            page_in = _page_inches(page)
            if page_in:
                pw_in, ph_in = page_in
                t_w = int(max(1, min(20000, round(pw_in * target_dpi))))
                t_h = int(max(1, min(20000, round(ph_in * target_dpi))))
            else:
                t_w = t_h = None

            for _, rawimg in _iter_image_xobjects(page, visited=visited):
                images_total += 1

                try:
                    if rawimg.get("/ImageMask", False) or ("/SMask" in rawimg) or ("/Mask" in rawimg):
                        images_skipped += 1
                        continue
                except Exception:
                    images_skipped += 1
                    continue

                try:
                    w0 = int(rawimg.get("/Width", 0))
                    h0 = int(rawimg.get("/Height", 0))
                    if w0 <= 0 or h0 <= 0 or (w0 * h0) < min_pixels:
                        images_skipped += 1
                        continue
                except Exception:
                    images_skipped += 1
                    continue

                old_raw = _stream_raw_size(rawimg)

                try:
                    pim = PdfImage(rawimg).as_pil_image()
                except Exception:
                    images_skipped += 1
                    continue

                if only_if_nearly_bilevel and (not _is_nearly_bilevel(pim)):
                    # gentle grayscale JPEG fallback, only if smaller
                    try:
                        g = pim.convert("L")
                        if t_w and t_h and (g.width > t_w or g.height > t_h):
                            scale = min(t_w / g.width, t_h / g.height)
                            g = g.resize((max(1, int(g.width * scale)), max(1, int(g.height * scale))), Image.Resampling.LANCZOS)

                        buf = BytesIO()
                        g.save(buf, format="JPEG", quality=int(max(40, min(95, fallback_jpeg_quality))), optimize=True, progressive=True)
                        jb = buf.getvalue()

                        if old_raw is not None and len(jb) >= old_raw:
                            images_skipped += 1
                            continue

                        rawimg.write(jb, filter=Name("/DCTDecode"))
                        rawimg.Width, rawimg.Height = g.width, g.height
                        rawimg.BitsPerComponent = 8
                        rawimg.ColorSpace = Name("/DeviceGray")
                        try:
                            if "/DecodeParms" in rawimg:
                                del rawimg["/DecodeParms"]
                        except Exception:
                            pass
                        images_fallback_jpeg += 1
                    except Exception:
                        images_skipped += 1
                    continue

                # grayscale + downsample
                try:
                    g = pim.convert("L")
                    if t_w and t_h and (g.width > t_w or g.height > t_h):
                        scale = min(t_w / g.width, t_h / g.height)
                        g = g.resize((max(1, int(g.width * scale)), max(1, int(g.height * scale))), Image.Resampling.LANCZOS)
                except Exception:
                    images_skipped += 1
                    continue

                # threshold to 1-bit
                try:
                    if threshold_mode == "auto":
                        thr = _otsu_threshold_from_hist(g.histogram())
                    else:
                        thr = int(max(0, min(255, manual_threshold)))
                    bw = g.point(lambda p: 255 if p > thr else 0, mode="1")
                except Exception:
                    images_skipped += 1
                    continue

                # CCITT encode, only if smaller
                try:
                    payload, inverted = _transcode_monochrome_to_ccitt_g4(bw)

                    if old_raw is not None and len(payload) >= old_raw:
                        images_skipped += 1
                        continue

                    rawimg.write(payload, filter=Name("/CCITTFaxDecode"))
                    rawimg.Width, rawimg.Height = bw.width, bw.height
                    rawimg.BitsPerComponent = 1
                    rawimg.ColorSpace = Name("/DeviceGray")
                    rawimg.DecodeParms = Dictionary({Name("/K"): -1, Name("/Columns"): bw.width, Name("/Rows"): bw.height})
                    rawimg.Decode = [1, 0] if inverted else [0, 1]
                    images_ccitt += 1
                except Exception:
                    # fallback grayscale JPEG, only if smaller
                    try:
                        buf = BytesIO()
                        g.save(buf, format="JPEG", quality=int(max(40, min(95, fallback_jpeg_quality))), optimize=True, progressive=True)
                        jb = buf.getvalue()

                        if old_raw is not None and len(jb) >= old_raw:
                            images_skipped += 1
                            continue

                        rawimg.write(jb, filter=Name("/DCTDecode"))
                        rawimg.Width, rawimg.Height = g.width, g.height
                        rawimg.BitsPerComponent = 8
                        rawimg.ColorSpace = Name("/DeviceGray")
                        try:
                            if "/DecodeParms" in rawimg:
                                del rawimg["/DecodeParms"]
                        except Exception:
                            pass
                        images_fallback_jpeg += 1
                    except Exception:
                        images_skipped += 1

        kwargs = {
            "compress_streams": True,
            "linearize": bool(linearize),
            "normalize_content": True,
            "recompress_flate": True,
            "compression_level": int(max(1, min(9, compression_level))),
        }
        if object_streams and hasattr(pikepdf, "ObjectStreamMode"):
            kwargs["object_stream_mode"] = pikepdf.ObjectStreamMode.generate

        out_bytes = _pikepdf_save_best(pdf, kwargs, original_size=len(input_bytes), try_harder=try_harder)
        note = f"Images total: {images_total}, CCITT: {images_ccitt}, fallback JPEG: {images_fallback_jpeg}, skipped: {images_skipped}"
        return out_bytes, "pikepdf(qpdf) ultra bw (internal)", note


def compress_ultra_bw_internal_best(
    input_bytes: bytes,
    *,
    password: str | None,
    remove_metadata: bool,
    base_target_dpi: int,
    min_megapixels: float,
    only_if_nearly_bilevel: bool,
    threshold_mode: str,
    manual_threshold: int,
    fallback_jpeg_quality: int,
    compression_level: int,
    object_streams: bool,
    linearize: bool,
    try_harder: bool,
    auto_optimize: bool,
    search_depth: int,
    target_reduction_pct: float | None,
    stop_when_target_met: bool,
) -> tuple[bytes, str, str]:
    original_size = len(input_bytes)
    target_size = None
    if target_reduction_pct is not None:
        target_size = int(original_size * (1.0 - max(0.0, min(0.95, target_reduction_pct / 100.0))))

    dpilist = [base_target_dpi]
    if auto_optimize:
        for d in (base_target_dpi - 40, base_target_dpi - 80, base_target_dpi - 120):
            if d >= 110:
                dpilist.append(d)
        dpilist = dpilist[: max(1, int(search_depth))]

    best_bytes = None
    best_backend = ""
    best_note = ""
    best_dpi = None

    for dpi in dpilist:
        b, backend, note = compress_ultra_bw_internal_once(
            input_bytes,
            password=password,
            remove_metadata=remove_metadata,
            target_dpi=int(dpi),
            min_megapixels=min_megapixels,
            only_if_nearly_bilevel=only_if_nearly_bilevel,
            threshold_mode=threshold_mode,
            manual_threshold=manual_threshold,
            fallback_jpeg_quality=fallback_jpeg_quality,
            compression_level=compression_level,
            object_streams=object_streams,
            linearize=linearize,
            try_harder=try_harder,
        )

        if best_bytes is None or len(b) < len(best_bytes):
            best_bytes, best_backend, best_note, best_dpi = b, backend, note, dpi

        if stop_when_target_met and target_size is not None and len(b) <= target_size:
            best_bytes, best_backend, best_note, best_dpi = b, backend, note, dpi
            break

    assert best_bytes is not None
    return best_bytes, best_backend, f"{best_note} | Best DPI={best_dpi}"


def compress_pdf_ultra_bw_ocrmypdf(
    input_bytes: bytes,
    *,
    password: str | None,
    remove_metadata: bool,
    optimize_level: int,
    jpg_quality: int | None,
    png_quality: int | None,
    jbig2_lossy: bool,
    skip_text: bool,
    try_harder: bool,
) -> tuple[bytes, str, str]:
    try:
        import ocrmypdf
    except ImportError as exc:
        raise ValueError("OCRmyPDF is not installed. Install: pip install ocrmypdf") from exc

    # Decrypt for OCRmyPDF if needed
    decrypted = input_bytes
    r = PdfReader(BytesIO(input_bytes))
    if r.is_encrypted:
        if not password:
            raise ValueError("This PDF is password-protected. Provide a password to continue.")
        if r.decrypt(password) == 0:
            raise ValueError("Unable to decrypt the PDF with the provided password.")
        w = PdfWriter()
        if hasattr(w, "clone_document_from_reader"):
            w.clone_document_from_reader(r)
        else:
            for p in r.pages:
                w.add_page(p)
        buf = BytesIO()
        w.write(buf)
        buf.seek(0)
        decrypted = buf.getvalue()

    inp = BytesIO(decrypted)
    inp.seek(0)
    out = BytesIO()

    kwargs = dict(
        optimize=int(max(0, min(3, optimize_level))),
        output_type="pdf",
        skip_text=bool(skip_text),
        use_threads=True,
        progress_bar=False,
        rotate_pages=False,
        deskew=False,
        clean=False,
        remove_background=False,
        redo_ocr=False,
        force_ocr=False,
        jobs=1,
        jbig2_lossy=bool(jbig2_lossy),
    )
    if jpg_quality is not None:
        kwargs["jpg_quality"] = int(jpg_quality)
    if png_quality is not None:
        kwargs["png_quality"] = int(png_quality)

    if _supports_kw(ocrmypdf.ocr, "ocr_engine"):
        kwargs["ocr_engine"] = "none"
    elif _supports_kw(ocrmypdf.ocr, "tesseract_timeout"):
        kwargs["tesseract_timeout"] = 0

    try:
        exit_code = ocrmypdf.ocr(inp, out, **kwargs)
    except Exception as exc:
        raise ValueError(f"OCRmyPDF failed: {exc}") from exc

    out.seek(0)
    out_bytes = out.getvalue()

    note = f"OCRmyPDF exit_code: {exit_code}"

    # Apply metadata policy + a qpdf-style tighten pass if pikepdf is available
    try:
        import pikepdf
        with pikepdf.open(BytesIO(decrypted)) as src_pdf, pikepdf.open(BytesIO(out_bytes)) as dst_pdf:
            if remove_metadata:
                _pikepdf_remove_metadata(dst_pdf)
            else:
                _pikepdf_copy_metadata(src_pdf, dst_pdf)

            kwargs2 = {
                "compress_streams": True,
                "linearize": False,
                "normalize_content": True,
                "recompress_flate": True,
                "compression_level": 9,
            }
            if hasattr(pikepdf, "ObjectStreamMode"):
                kwargs2["object_stream_mode"] = pikepdf.ObjectStreamMode.generate

            out_bytes = _pikepdf_save_best(dst_pdf, kwargs2, original_size=len(decrypted), try_harder=try_harder)
    except Exception:
        pass

    return out_bytes, "OCRmyPDF ultra bw (optimize-only)", note


# =========================
# Streamlit UI
# =========================
st.set_page_config(page_title="PDF Compressor", page_icon="🗜️", layout="centered")
st.title("PDF Compressor")
st.write(
    "Reality check: **5–10%** is normal for already-optimized digital PDFs. "
    "**50–90%** happens mainly for scan-heavy PDFs when you allow downsampling / B&W."
)

with st.sidebar:
    st.subheader("Mode")
    mode = st.selectbox(
        "Compression mode",
        options=[
            "Lossless (exact)",
            "Scan/Turbo (JPEG, visually-lossless for scans)",
            "Ultra B/W (JBIG2/CCITT for monochrome scans)",
        ],
        index=0,
    )

    st.subheader("Common")
    remove_metadata = st.checkbox("Remove metadata (Info + XMP)", value=False)
    keep_smaller_only = st.checkbox("Keep original if compression increases size", value=True)
    try_harder = st.checkbox("Try harder when size increases (slower)", value=True)
    show_analysis = st.checkbox("Show PDF analysis (why compression is limited)", value=True)

    st.subheader("Goal")
    use_target = st.checkbox("Try to reach target reduction % (best effort)", value=False)
    target_reduction = st.slider("Target reduction %", 0, 90, 50) if use_target else None
    stop_when_target_met = st.checkbox("Stop once target is met (preserve quality)", value=True) if use_target else False

    output_suffix = st.text_input("Output filename suffix", value="-compressed")
    password = st.text_input("Password (only if PDF is protected)", type="password", placeholder="Leave blank if not needed")
    pw = password or None

    st.subheader("Save tuning")
    compression_level = st.slider("Lossless stream recompression level", 1, 9, 9)
    object_streams = st.checkbox("Use object streams (PDF 1.5+)", value=True)
    linearize = st.checkbox("Fast web view (linearize)", value=False)

    # Lossless options
    if mode.startswith("Lossless"):
        st.subheader("Lossless backend")
        backend = st.selectbox("Backend", ["auto (recommended)", "pikepdf (best)", "PyPDF2 (fallback)"], index=0)
        backend_key = {
            "auto (recommended)": "auto",
            "pikepdf (best)": "pikepdf",
            "PyPDF2 (fallback)": "pypdf2",
        }[backend]

    # Scan/Turbo options
    if mode.startswith("Scan/Turbo"):
        st.subheader("Scan/Turbo preset")
        preset = st.selectbox("Preset", ["Balanced", "Strong", "Extreme", "Custom"], index=1)
        if preset == "Balanced":
            base_dpi, base_q, base_gs, min_megapixels = 300, 90, False, 0.50
        elif preset == "Strong":
            base_dpi, base_q, base_gs, min_megapixels = 220, 85, False, 0.50
        elif preset == "Extreme":
            base_dpi, base_q, base_gs, min_megapixels = 170, 75, True, 0.75
        else:
            base_dpi = st.slider("Target DPI", 100, 450, 220, step=10)
            base_q = st.slider("JPEG quality", 50, 95, 85)
            base_gs = st.checkbox("Convert images to grayscale", value=False)
            min_megapixels = st.slider("Only touch images >= MP", 0.10, 5.00, 0.50, step=0.10)

        auto_opt = st.checkbox("Auto-optimize (try multiple settings & pick best)", value=True)
        search_depth = st.slider("Auto-optimize search depth", 1, 12, 8) if auto_opt else 1

    # Ultra B/W options
    if mode.startswith("Ultra B/W"):
        st.subheader("Ultra B/W engine")
        ultra_engine = st.selectbox(
            "Engine",
            ["auto (try OCRmyPDF, else internal CCITT)", "OCRmyPDF (best if available)", "internal CCITT G4 (pure Python)"],
            index=0,
        )

        st.subheader("Ultra B/W tuning")
        bw_preset = st.selectbox("Preset", ["Safe", "Strong", "Aggressive", "Custom"], index=1)
        if bw_preset == "Safe":
            bw_dpi, bw_min_mp, only_bilevel, fallback_q = 300, 0.50, True, 85
        elif bw_preset == "Strong":
            bw_dpi, bw_min_mp, only_bilevel, fallback_q = 220, 0.50, True, 80
        elif bw_preset == "Aggressive":
            bw_dpi, bw_min_mp, only_bilevel, fallback_q = 170, 0.75, False, 75
        else:
            bw_dpi = st.slider("Target DPI (B/W)", 110, 450, 220, step=10)
            bw_min_mp = st.slider("Only touch images >= MP", 0.10, 5.00, 0.50, step=0.10)
            only_bilevel = st.checkbox("Only CCITT if image is nearly bilevel", value=True)
            fallback_q = st.slider("Fallback JPEG(gray) quality", 50, 95, 80)

        threshold_mode_ui = st.selectbox("Threshold", ["auto (Otsu)", "manual"], index=0)
        threshold_mode = "auto" if threshold_mode_ui.startswith("auto") else "manual"
        manual_threshold = st.slider("Manual threshold", 0, 255, 180) if threshold_mode == "manual" else 180

        bw_auto_opt = st.checkbox("Auto-optimize DPI (try multiple & pick best)", value=True)
        bw_search_depth = st.slider("Auto-optimize search depth", 1, 4, 3) if bw_auto_opt else 1

        st.subheader("OCRmyPDF options (if used)")
        ocr_opt = st.slider("OCRmyPDF optimize level", 0, 3, 3)
        ocr_skip_text = st.checkbox("Skip pages that already have text", value=True)
        ocr_jbig2_lossy = st.checkbox("JBIG2 lossy (riskier, smaller)", value=False)
        ocr_jpg_q = st.checkbox("Set OCRmyPDF JPEG quality", value=True)
        ocr_jpg_quality = st.slider("OCRmyPDF jpg_quality", 50, 95, 80) if ocr_jpg_q else None
        ocr_png_q = st.checkbox("Set OCRmyPDF PNG quality", value=False)
        ocr_png_quality = st.slider("OCRmyPDF png_quality", 0, 100, 80) if ocr_png_q else None


uploaded_files = st.file_uploader("Upload PDF files", type=["pdf"], accept_multiple_files=True)

if uploaded_files:
    results: list[CompressionResult] = []
    errors: list[str] = []

    prog = st.progress(0.0)

    for i, uploaded_file in enumerate(uploaded_files, start=1):
        try:
            original_bytes = uploaded_file.getvalue()
            original_size = len(original_bytes)

            analysis = analyze_pdf_bytes(original_bytes, password=pw) if show_analysis else None

            if mode.startswith("Lossless"):
                attempted_bytes, used_backend, note = compress_pdf_lossless(
                    original_bytes,
                    password=pw,
                    remove_metadata=remove_metadata,
                    backend=backend_key,
                    compression_level=compression_level,
                    object_streams=object_streams,
                    linearize=linearize,
                    try_harder=try_harder,
                )

            elif mode.startswith("Scan/Turbo"):
                attempted_bytes, used_backend, note = compress_pdf_scan_turbo_best(
                    original_bytes,
                    password=pw,
                    remove_metadata=remove_metadata,
                    base_target_dpi=base_dpi,
                    base_quality=base_q,
                    base_grayscale=base_gs,
                    min_megapixels=min_megapixels,
                    compression_level=compression_level,
                    object_streams=object_streams,
                    linearize=linearize,
                    try_harder=try_harder,
                    auto_optimize=auto_opt,
                    search_depth=search_depth,
                    target_reduction_pct=target_reduction,
                    stop_when_target_met=stop_when_target_met,
                )

            else:
                def _try_ocrmypdf_first() -> bool:
                    return ultra_engine.startswith("auto") or ultra_engine.startswith("OCRmyPDF")

                attempted_bytes = b""
                used_backend = ""
                note = ""

                if _try_ocrmypdf_first():
                    try:
                        attempted_bytes, used_backend, note = compress_pdf_ultra_bw_ocrmypdf(
                            original_bytes,
                            password=pw,
                            remove_metadata=remove_metadata,
                            optimize_level=ocr_opt,
                            jpg_quality=ocr_jpg_quality,
                            png_quality=ocr_png_quality,
                            jbig2_lossy=ocr_jbig2_lossy,
                            skip_text=ocr_skip_text,
                            try_harder=try_harder,
                        )
                    except Exception as exc:
                        if ultra_engine.startswith("OCRmyPDF"):
                            raise
                        note = f"OCRmyPDF unavailable/failed -> fallback internal CCITT. ({exc})"
                        attempted_bytes = b""
                        used_backend = ""

                if not attempted_bytes:
                    attempted_bytes, used_backend2, note2 = compress_ultra_bw_internal_best(
                        original_bytes,
                        password=pw,
                        remove_metadata=remove_metadata,
                        base_target_dpi=bw_dpi,
                        min_megapixels=bw_min_mp,
                        only_if_nearly_bilevel=only_bilevel,
                        threshold_mode=threshold_mode,
                        manual_threshold=manual_threshold,
                        fallback_jpeg_quality=fallback_q,
                        compression_level=compression_level,
                        object_streams=object_streams,
                        linearize=linearize,
                        try_harder=try_harder,
                        auto_optimize=bw_auto_opt,
                        search_depth=bw_search_depth,
                        target_reduction_pct=target_reduction,
                        stop_when_target_met=stop_when_target_met,
                    )
                    used_backend = used_backend or used_backend2
                    note = f"{note}\n{note2}".strip()

            attempted_size = len(attempted_bytes)

            output_bytes = attempted_bytes
            used_original = False
            if keep_smaller_only and attempted_size >= original_size:
                output_bytes = original_bytes
                used_original = True

            output_size = len(output_bytes)

            results.append(
                CompressionResult(
                    filename=build_output_name(uploaded_file.name, output_suffix),
                    original_size=original_size,
                    attempted_size=attempted_size,
                    output_size=output_size,
                    data=output_bytes,
                    used_original=used_original,
                    backend=used_backend,
                    note=note,
                    analysis=analysis,
                )
            )
        except Exception as exc:
            errors.append(f"{uploaded_file.name}: {exc}")

        prog.progress(i / max(1, len(uploaded_files)))

    if errors:
        st.error("Some files could not be processed:")
        for msg in errors:
            st.write(f"- {msg}")

    if results:
        results = dedupe_names(results)
        st.subheader("Results")

        for r in results:
            ratio = 0.0 if r.original_size == 0 else (1 - r.output_size / r.original_size) * 100
            status_note = " (kept original)" if r.used_original else ""
            st.write(
                f"**{r.filename}** — {format_size(r.original_size)} → {format_size(r.output_size)} "
                f"({ratio:.1f}% reduction){status_note}\n\n"
                f"Engine: `{r.backend}`"
            )

            if r.used_original:
                delta = r.attempted_size - r.original_size
                sign = "+" if delta >= 0 else ""
                st.caption(
                    f"Best attempt was {format_size(r.attempted_size)} ({sign}{format_size(abs(delta))} vs original), "
                    f"so original was kept."
                )

            if r.note:
                st.caption(r.note)

            if r.analysis:
                with st.expander("Why compression may be limited (analysis)"):
                    a = r.analysis
                    st.write(f"- Pages: **{a.get('pages')}**")
                    st.write(f"- Images: **{a.get('image_count')}**")
                    st.write(f"- Image share of file (approx): **{a.get('image_share_of_file', 0.0)*100:.1f}%**")
                    st.write(f"- Likely scanned: **{a.get('likely_scanned')}**")
                    st.write(f"- JPEG-heavy already (DCTDecode): **{a.get('already_jpeg_heavy')}**")
                    st.write("- Filters found (top):")
                    for k, v in list((a.get("filters") or {}).items())[:8]:
                        st.write(f"  - {k}: {v}")

            st.download_button(
                label=f"Download {r.filename}",
                data=r.data,
                file_name=r.filename,
                mime="application/pdf",
            )

        if len(results) > 1:
            zip_bytes = build_zip(results)
            st.download_button(
                label="Download all as ZIP",
                data=zip_bytes,
                file_name="compressed_pdfs.zip",
                mime="application/zip",
            )
else:
    st.info("Upload at least one PDF to see compression results.")
