from __future__ import annotations

import inspect
import logging
import math
import re
import zlib
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
    compressed_size: int
    data: bytes
    used_original: bool = False
    backend: str = "auto"
    note: str = ""


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
                compressed_size=r.compressed_size,
                data=r.data,
                used_original=r.used_original,
                backend=r.backend,
                note=r.note,
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
    # Accept if **kwargs present
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
    """pikepdf versions vary; drop unknown kwargs until save() works."""
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


def _pikepdf_remove_metadata(pdf) -> None:
    try:
        # remove XMP
        if "/Metadata" in pdf.Root:
            del pdf.Root["/Metadata"]
    except Exception:
        pass
    try:
        # remove DocInfo
        pdf.docinfo.clear()
    except Exception:
        pass


def _pikepdf_copy_metadata(src_pdf, dst_pdf) -> None:
    """Best-effort metadata preservation for both XMP + DocInfo."""
    try:
        # Copy DocInfo keys
        try:
            dst_pdf.docinfo.clear()
            for k, v in src_pdf.docinfo.items():
                dst_pdf.docinfo[k] = v
        except Exception:
            pass

        # Copy XMP via open_metadata mapping
        try:
            src_meta = src_pdf.open_metadata()
            with dst_pdf.open_metadata() as dst_meta:
                # Clear existing keys first
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


def _compress_with_pikepdf_lossless(
    input_bytes: bytes,
    *,
    password: str | None,
    remove_metadata: bool,
    compression_level: int,
    object_streams: bool,
    linearize: bool,
) -> bytes:
    import pikepdf

    try:
        pdf = pikepdf.open(BytesIO(input_bytes), password=password)
    except Exception as exc:
        PasswordError = getattr(pikepdf, "PasswordError", None)
        PdfError = getattr(pikepdf, "PdfError", None)
        if PasswordError and isinstance(exc, PasswordError):
            raise ValueError("Unable to decrypt the PDF with the provided password.")
        if PdfError and isinstance(exc, PdfError):
            raise ValueError("The file could not be read as a PDF.")
        raise

    with pdf:
        if remove_metadata:
            _pikepdf_remove_metadata(pdf)

        out = BytesIO()
        kwargs = {
            "compress_streams": True,
            "linearize": bool(linearize),
            "normalize_content": True,
            "recompress_flate": True,
            "compression_level": int(max(1, min(9, compression_level))),
        }
        if object_streams and hasattr(pikepdf, "ObjectStreamMode"):
            kwargs["object_stream_mode"] = pikepdf.ObjectStreamMode.generate

        _safe_pikepdf_save(pdf, out, kwargs)
        out.seek(0)
        return out.getvalue()


def compress_pdf_lossless(
    input_bytes: bytes,
    *,
    password: str | None = None,
    remove_metadata: bool = False,
    backend: str = "auto",  # auto | pikepdf | pypdf2
    compression_level: int = 9,
    object_streams: bool = True,
    linearize: bool = False,
) -> tuple[bytes, str]:
    backend = backend.lower().strip()

    if backend in {"auto", "pikepdf"}:
        try:
            out = _compress_with_pikepdf_lossless(
                input_bytes,
                password=password,
                remove_metadata=remove_metadata,
                compression_level=compression_level,
                object_streams=object_streams,
                linearize=linearize,
            )
            return out, "pikepdf(qpdf) lossless"
        except ImportError:
            if backend == "pikepdf":
                raise ValueError("Backend 'pikepdf' selected but pikepdf is not installed.")
        except Exception:
            if backend == "pikepdf":
                raise

    out = _compress_with_pypdf2_lossless(input_bytes, password=password, remove_metadata=remove_metadata)
    return out, "PyPDF2 lossless"


# =========================
# Image scanning: recursive XObject traversal
# =========================
def _iter_image_xobjects(obj, *, visited: set[tuple[int, int]]):
    """
    Yield (name, image_stream_obj) for images found in obj's Resources/XObject,
    recursing into /Form XObjects.
    """
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
            # Identify object uniquely (to avoid reprocessing shared images)
            og = getattr(xo, "objgen", None)
            if og and og in visited:
                continue
            if og:
                visited.add(og)

            subtype = xo.get("/Subtype", None)
            if subtype == "/Image":
                yield (name, xo)
            elif subtype == "/Form":
                # Recurse
                yield from _iter_image_xobjects(xo, visited=visited)
        except Exception:
            continue


def _page_inches(page) -> tuple[float, float] | None:
    # MediaBox is points (72 per inch)
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
# Scan/Turbo: JPEG re-encode (visually lossless for scans)
# =========================
def compress_pdf_scan_turbo(
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
) -> tuple[bytes, str, str]:
    try:
        import pikepdf
        from pikepdf import PdfImage, Name
        from PIL import Image
    except ImportError as exc:
        raise ValueError("Scan/Turbo mode requires pikepdf + pillow. Install: pip install pikepdf pillow") from exc

    # Avoid PIL DecompressionBomb warnings for large scans (still can OOM if gigantic)
    Image.MAX_IMAGE_PIXELS = None

    try:
        pdf = pikepdf.open(BytesIO(input_bytes), password=password)
    except Exception as exc:
        PasswordError = getattr(pikepdf, "PasswordError", None)
        PdfError = getattr(pikepdf, "PdfError", None)
        if PasswordError and isinstance(exc, PasswordError):
            raise ValueError("Unable to decrypt the PDF with the provided password.")
        if PdfError and isinstance(exc, PdfError):
            raise ValueError("The file could not be read as a PDF.")
        raise

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

                # Skip masks/transparency (these are easy to break)
                try:
                    if rawimg.get("/ImageMask", False):
                        images_skipped += 1
                        continue
                    if "/SMask" in rawimg or "/Mask" in rawimg:
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

                try:
                    rawimg.write(jpeg_bytes, filter=Name("/DCTDecode"))
                    rawimg.Width, rawimg.Height = pim.width, pim.height
                    rawimg.BitsPerComponent = 8
                    rawimg.ColorSpace = Name("/DeviceGray") if grayscale else Name("/DeviceRGB")
                    # Remove decode parms that apply to Flate-style encodings
                    try:
                        if "/DecodeParms" in rawimg:
                            del rawimg["/DecodeParms"]
                    except Exception:
                        pass
                    images_optimized += 1
                except Exception:
                    images_skipped += 1
                    continue

        out = BytesIO()
        kwargs = {
            "compress_streams": True,
            "linearize": bool(linearize),
            "normalize_content": True,
            "recompress_flate": True,
            "compression_level": int(max(1, min(9, compression_level))),
        }
        if object_streams and hasattr(pikepdf, "ObjectStreamMode"):
            kwargs["object_stream_mode"] = pikepdf.ObjectStreamMode.generate

        _safe_pikepdf_save(pdf, out, kwargs)
        out.seek(0)
        note = f"Images total: {images_total}, optimized: {images_optimized}, skipped: {images_skipped}"
        return out.getvalue(), "pikepdf(qpdf) scan/turbo", note


# =========================
# Ultra B/W: CCITT Group4 internal (pure Python, requires libtiff in Pillow)
# =========================
def _bitrev_table() -> bytes:
    # 256-byte lookup table for bit reversal
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
    # Extract CCITT strip payload location from TIFF tags
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
    # Histogram-based: proportion near black or near white
    try:
        g = pil_img.convert("L")
        # Downsample for speed
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
    """
    Convert a 1-bit PIL image to raw CCITT Group4 payload + inversion flag.
    Requires Pillow built with libtiff support.
    """
    from PIL import Image, TiffImagePlugin, features as PIL_features

    if not PIL_features.check("libtiff"):
        raise RuntimeError("Pillow is not compiled with libtiff; cannot encode Group4 CCITT.")

    # Write a Group4 TIFF in-memory (force single strip), then extract raw payload
    newimgio = BytesIO()
    img2 = Image.frombytes(pil_bw_1bit.mode, pil_bw_1bit.size, pil_bw_1bit.tobytes())

    tmp_strip_size = (pil_bw_1bit.size[0] + 7) // 8 * pil_bw_1bit.size[1]

    if hasattr(TiffImagePlugin, "STRIP_SIZE"):
        with _temp_attr(TiffImagePlugin, "STRIP_SIZE", tmp_strip_size):
            img2.save(newimgio, format="TIFF", compression="group4")
    else:
        # Old Pillow fallback (rare now)
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

    # Determine inversion (TIFF photometric)
    photo = tiff_img.tag_v2[TiffImagePlugin.PHOTOMETRIC_INTERPRETATION]
    inverted = False
    if photo == 0:
        inverted = True
    elif photo == 1:
        inverted = False

    offset, length = _ccitt_payload_location_from_pil(tiff_img)
    newimgio.seek(offset)
    payload = newimgio.read(length)

    # Handle FillOrder if needed
    fillorder = tiff_img.tag_v2.get(TiffImagePlugin.FILLORDER)
    if fillorder == 2:
        payload = bytes(TIFF_BITREV[b] for b in payload)

    return payload, inverted


def compress_pdf_ultra_bw_internal_ccitt(
    input_bytes: bytes,
    *,
    password: str | None,
    remove_metadata: bool,
    target_dpi: int,
    min_megapixels: float,
    only_if_nearly_bilevel: bool,
    threshold_mode: str,  # "auto" | "manual"
    manual_threshold: int,
    fallback_jpeg_quality: int,
    compression_level: int,
    object_streams: bool,
    linearize: bool,
) -> tuple[bytes, str, str]:
    try:
        import pikepdf
        from pikepdf import PdfImage, Name, Dictionary
        from PIL import Image
    except ImportError as exc:
        raise ValueError("Ultra B/W internal CCITT requires pikepdf + pillow.") from exc

    Image.MAX_IMAGE_PIXELS = None

    try:
        pdf = pikepdf.open(BytesIO(input_bytes), password=password)
    except Exception as exc:
        PasswordError = getattr(pikepdf, "PasswordError", None)
        PdfError = getattr(pikepdf, "PdfError", None)
        if PasswordError and isinstance(exc, PasswordError):
            raise ValueError("Unable to decrypt the PDF with the provided password.")
        if PdfError and isinstance(exc, PdfError):
            raise ValueError("The file could not be read as a PDF.")
        raise

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

                # Skip masks/transparency
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

                try:
                    pim = PdfImage(rawimg).as_pil_image()
                except Exception:
                    images_skipped += 1
                    continue

                # Optional bilevel-likeliness test (to avoid destroying grayscale photos)
                if only_if_nearly_bilevel and (not _is_nearly_bilevel(pim)):
                    # Not bilevel-ish: fallback to grayscale JPEG (still big savings, less harsh)
                    try:
                        g = pim.convert("L")
                        if t_w and t_h and (g.width > t_w or g.height > t_h):
                            scale = min(t_w / g.width, t_h / g.height)
                            g = g.resize((max(1, int(g.width * scale)), max(1, int(g.height * scale))), Image.Resampling.LANCZOS)

                        buf = BytesIO()
                        g.save(buf, format="JPEG", quality=int(max(40, min(95, fallback_jpeg_quality))), optimize=True, progressive=True)
                        rawimg.write(buf.getvalue(), filter=Name("/DCTDecode"))
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

                # Convert to grayscale and downsample
                try:
                    g = pim.convert("L")
                    if t_w and t_h and (g.width > t_w or g.height > t_h):
                        scale = min(t_w / g.width, t_h / g.height)
                        g = g.resize((max(1, int(g.width * scale)), max(1, int(g.height * scale))), Image.Resampling.LANCZOS)
                except Exception:
                    images_skipped += 1
                    continue

                # Threshold to 1-bit
                try:
                    if threshold_mode == "auto":
                        hist = g.histogram()
                        thr = _otsu_threshold_from_hist(hist)
                    else:
                        thr = int(max(0, min(255, manual_threshold)))
                    bw = g.point(lambda p: 255 if p > thr else 0, mode="1")
                except Exception:
                    images_skipped += 1
                    continue

                # Encode CCITT G4 and replace
                try:
                    payload, inverted = _transcode_monochrome_to_ccitt_g4(bw)
                    rawimg.write(payload, filter=Name("/CCITTFaxDecode"))
                    rawimg.Width, rawimg.Height = bw.width, bw.height
                    rawimg.BitsPerComponent = 1
                    rawimg.ColorSpace = Name("/DeviceGray")
                    rawimg.DecodeParms = Dictionary(
                        {
                            Name("/K"): -1,  # Group4
                            Name("/Columns"): bw.width,
                            Name("/Rows"): bw.height,
                        }
                    )
                    rawimg.Decode = [1, 0] if inverted else [0, 1]
                    images_ccitt += 1
                except Exception:
                    # If CCITT fails (no libtiff), fallback to grayscale JPEG
                    try:
                        buf = BytesIO()
                        g2 = g
                        buf = BytesIO()
                        g2.save(buf, format="JPEG", quality=int(max(40, min(95, fallback_jpeg_quality))), optimize=True, progressive=True)
                        rawimg.write(buf.getvalue(), filter=Name("/DCTDecode"))
                        rawimg.Width, rawimg.Height = g2.width, g2.height
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

        out = BytesIO()
        kwargs = {
            "compress_streams": True,
            "linearize": bool(linearize),
            "normalize_content": True,
            "recompress_flate": True,
            "compression_level": int(max(1, min(9, compression_level))),
        }
        if object_streams and hasattr(pikepdf, "ObjectStreamMode"):
            kwargs["object_stream_mode"] = pikepdf.ObjectStreamMode.generate

        _safe_pikepdf_save(pdf, out, kwargs)
        out.seek(0)
        note = (
            f"Images total: {images_total}, CCITT(G4): {images_ccitt}, "
            f"fallback JPEG(gray): {images_fallback_jpeg}, skipped: {images_skipped}"
        )
        return out.getvalue(), "pikepdf(qpdf) ultra bw (internal)", note


# =========================
# Ultra B/W: OCRmyPDF optimize-only (no OCR)
# =========================
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
) -> tuple[bytes, str, str]:
    try:
        import ocrmypdf
    except ImportError as exc:
        raise ValueError("OCRmyPDF is not installed. Install: pip install ocrmypdf") from exc

    # OCRmyPDF does not accept encrypted PDFs with a password parameter → decrypt first
    decrypted = input_bytes
    try:
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
    except Exception:
        # If decryption check fails, we still try OCRmyPDF; it will error if encrypted.
        decrypted = input_bytes

    inp = BytesIO(decrypted)
    out = BytesIO()

    # Keep Streamlit stable: use_threads avoids multiprocessing/fork pain
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

    # Disable OCR:
    # v17+: ocr_engine='none'
    # older idiom: tesseract_timeout=0
    if _supports_kw(ocrmypdf.ocr, "ocr_engine"):
        kwargs["ocr_engine"] = "none"
    elif _supports_kw(ocrmypdf.ocr, "tesseract_timeout"):
        kwargs["tesseract_timeout"] = 0

    # Run
    try:
        exit_code = ocrmypdf.ocr(inp, out, **kwargs)
    except Exception as exc:
        raise ValueError(f"OCRmyPDF failed: {exc}") from exc

    out.seek(0)
    out_bytes = out.getvalue()

    # Postprocess metadata (remove or preserve original as requested)
    try:
        import pikepdf
        with pikepdf.open(BytesIO(decrypted)) as src_pdf, pikepdf.open(BytesIO(out_bytes)) as dst_pdf:
            if remove_metadata:
                _pikepdf_remove_metadata(dst_pdf)
            else:
                _pikepdf_copy_metadata(src_pdf, dst_pdf)
            out2 = BytesIO()
            dst_pdf.save(out2)
            out2.seek(0)
            out_bytes = out2.getvalue()
    except Exception:
        # If pikepdf not available, leave as-is
        pass

    note = f"OCRmyPDF exit_code: {exit_code}"
    return out_bytes, "OCRmyPDF ultra bw (optimize-only)", note


# =========================
# Streamlit UI
# =========================
st.set_page_config(page_title="PDF Compressor", page_icon="🗜️", layout="centered")
st.title("PDF Compressor")
st.write(
    "Three modes: **Lossless (exact)**, **Scan/Turbo (big savings for scans)**, "
    "and **Ultra B/W (best for monochrome text scans)**."
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

    st.subheader("Common options")
    remove_metadata = st.checkbox("Remove metadata (Info + XMP)", value=False)
    keep_smaller_only = st.checkbox("Keep original if compression increases size", value=True)
    output_suffix = st.text_input("Output filename suffix", value="-compressed")
    password = st.text_input("Password (only if PDF is protected)", type="password", placeholder="Leave blank if not needed")

    # Common save tuning
    compression_level = st.slider("Lossless stream recompression level", 1, 9, 9)
    object_streams = st.checkbox("Use object streams (PDF 1.5+)", value=True)
    linearize = st.checkbox("Fast web view (linearize)", value=False)

    # Lossless options
    if mode.startswith("Lossless"):
        st.subheader("Lossless engine")
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
            target_dpi, jpeg_quality, grayscale, min_megapixels = 300, 90, False, 0.50
        elif preset == "Strong":
            target_dpi, jpeg_quality, grayscale, min_megapixels = 220, 85, False, 0.50
        elif preset == "Extreme":
            target_dpi, jpeg_quality, grayscale, min_megapixels = 170, 75, True, 0.75
        else:
            target_dpi = st.slider("Target DPI", 100, 450, 220, step=10)
            jpeg_quality = st.slider("JPEG quality", 50, 95, 85)
            grayscale = st.checkbox("Convert images to grayscale", value=False)
            min_megapixels = st.slider("Only touch images >= MP", 0.10, 5.00, 0.50, step=0.10)

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
            bw_target_dpi, bw_min_mp, only_if_nearly_bilevel, fallback_q = 300, 0.50, True, 85
        elif bw_preset == "Strong":
            bw_target_dpi, bw_min_mp, only_if_nearly_bilevel, fallback_q = 220, 0.50, True, 80
        elif bw_preset == "Aggressive":
            bw_target_dpi, bw_min_mp, only_if_nearly_bilevel, fallback_q = 180, 0.75, False, 75
        else:
            bw_target_dpi = st.slider("Target DPI (B/W)", 120, 450, 220, step=10)
            bw_min_mp = st.slider("Only touch images >= MP", 0.10, 5.00, 0.50, step=0.10)
            only_if_nearly_bilevel = st.checkbox("Only CCITT if image is nearly bilevel", value=True)
            fallback_q = st.slider("Fallback JPEG(gray) quality (if CCITT not applied)", 50, 95, 80)

        threshold_mode = st.selectbox("Threshold", ["auto (Otsu)", "manual"], index=0)
        manual_threshold = st.slider("Manual threshold", 0, 255, 180) if threshold_mode == "manual" else 180

        st.subheader("OCRmyPDF options (if used)")
        ocr_opt = st.slider("OCRmyPDF optimize level", 0, 3, 3)
        ocr_skip_text = st.checkbox("Skip pages that already have text", value=True)
        ocr_jbig2_lossy = st.checkbox("JBIG2 lossy (risky, smaller)", value=False)
        ocr_jpg_q = st.checkbox("Set OCRmyPDF JPEG quality", value=True)
        ocr_jpg_quality = st.slider("OCRmyPDF jpg_quality", 50, 95, 80) if ocr_jpg_q else None
        ocr_png_q = st.checkbox("Set OCRmyPDF PNG quality", value=False)
        ocr_png_quality = st.slider("OCRmyPDF png_quality", 0, 100, 80) if ocr_png_q else None


uploaded_files = st.file_uploader("Upload PDF files", type=["pdf"], accept_multiple_files=True)

if uploaded_files:
    results: list[CompressionResult] = []
    errors: list[str] = []

    prog = st.progress(0)
    for i, uploaded_file in enumerate(uploaded_files, start=1):
        try:
            original_bytes = uploaded_file.getvalue()

            if mode.startswith("Lossless"):
                compressed_bytes, used_backend = compress_pdf_lossless(
                    original_bytes,
                    password=password or None,
                    remove_metadata=remove_metadata,
                    backend=backend_key,
                    compression_level=compression_level,
                    object_streams=object_streams,
                    linearize=linearize,
                )
                note = "Exact visuals preserved."

            elif mode.startswith("Scan/Turbo"):
                compressed_bytes, used_backend, note = compress_pdf_scan_turbo(
                    original_bytes,
                    password=password or None,
                    remove_metadata=remove_metadata,
                    target_dpi=target_dpi,
                    jpeg_quality=jpeg_quality,
                    grayscale=grayscale,
                    min_megapixels=min_megapixels,
                    compression_level=compression_level,
                    object_streams=object_streams,
                    linearize=linearize,
                )

            else:
                # Ultra B/W
                def _try_ocrmypdf_first() -> bool:
                    return ultra_engine.startswith("auto") or ultra_engine.startswith("OCRmyPDF")

                used_backend = ""
                note = ""
                compressed_bytes = b""

                if _try_ocrmypdf_first():
                    try:
                        compressed_bytes, used_backend, note = compress_pdf_ultra_bw_ocrmypdf(
                            original_bytes,
                            password=password or None,
                            remove_metadata=remove_metadata,
                            optimize_level=ocr_opt,
                            jpg_quality=ocr_jpg_quality,
                            png_quality=ocr_png_quality,
                            jbig2_lossy=ocr_jbig2_lossy,
                            skip_text=ocr_skip_text,
                        )
                    except Exception as exc:
                        # Auto falls back; explicit OCRmyPDF shows error
                        if ultra_engine.startswith("OCRmyPDF"):
                            raise
                        note = f"OCRmyPDF unavailable/failed -> fallback internal CCITT. ({exc})"
                        compressed_bytes = b""
                        used_backend = ""

                if not compressed_bytes:
                    compressed_bytes, used_backend2, note2 = compress_pdf_ultra_bw_internal_ccitt(
                        original_bytes,
                        password=password or None,
                        remove_metadata=remove_metadata,
                        target_dpi=bw_target_dpi,
                        min_megapixels=bw_min_mp,
                        only_if_nearly_bilevel=only_if_nearly_bilevel,
                        threshold_mode="auto" if threshold_mode.startswith("auto") else "manual",
                        manual_threshold=manual_threshold,
                        fallback_jpeg_quality=fallback_q,
                        compression_level=compression_level,
                        object_streams=object_streams,
                        linearize=linearize,
                    )
                    used_backend = used_backend or used_backend2
                    note = f"{note}\n{note2}".strip()

            output_bytes = compressed_bytes
            used_original = False
            if keep_smaller_only and len(compressed_bytes) >= len(original_bytes):
                output_bytes = original_bytes
                used_original = True

            results.append(
                CompressionResult(
                    filename=build_output_name(uploaded_file.name, output_suffix),
                    original_size=len(original_bytes),
                    compressed_size=len(compressed_bytes),
                    data=output_bytes,
                    used_original=used_original,
                    backend=used_backend,
                    note=note,
                )
            )
        except Exception as exc:
            errors.append(f"{uploaded_file.name}: {exc}")

        prog.progress(int(i / max(1, len(uploaded_files)) * 100))

    if errors:
        st.error("Some files could not be processed:")
        for msg in errors:
            st.write(f"- {msg}")

    if results:
        results = dedupe_names(results)
        st.subheader("Results")

        for r in results:
            ratio = 0.0 if r.original_size == 0 else (1 - r.compressed_size / r.original_size) * 100
            status_note = " (kept original)" if r.used_original else ""
            st.write(
                f"**{r.filename}** — {format_size(r.original_size)} → {format_size(r.compressed_size)} "
                f"({ratio:.1f}% reduction){status_note}\n\n"
                f"Engine: `{r.backend}`  \n{r.note}"
            )
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
