from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Iterable
from zipfile import ZipFile

import streamlit as st
from PyPDF2 import PdfReader, PdfWriter
from PyPDF2.errors import PdfReadError


@dataclass
class CompressionResult:
    filename: str
    original_size: int
    compressed_size: int
    data: bytes
    used_original: bool = False


def format_size(num_bytes: int) -> str:
    if num_bytes < 1024:
        return f"{num_bytes} B"
    if num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.2f} KB"
    return f"{num_bytes / 1024 / 1024:.2f} MB"


def compress_pdf(
    input_bytes: bytes,
    *,
    password: str | None = None,
    remove_metadata: bool = False,
) -> bytes:
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
    for page in reader.pages:
        page.compress_content_streams()
        writer.add_page(page)

    if not remove_metadata and reader.metadata:
        metadata = {
            key: str(value)
            for key, value in reader.metadata.items()
            if value is not None
        }
        if metadata:
            writer.add_metadata(metadata)

    output_buffer = BytesIO()
    writer.write(output_buffer)
    output_buffer.seek(0)
    return output_buffer.getvalue()


def build_zip(results: Iterable[CompressionResult]) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as zip_handle:
        for result in results:
            zip_handle.writestr(result.filename, result.data)
    buffer.seek(0)
    return buffer.getvalue()


def build_output_name(filename: str, suffix: str) -> str:
    path = Path(filename)
    if not path.suffix:
        return f"{filename}{suffix}.pdf"
    return f"{path.stem}{suffix}{path.suffix}"


def dedupe_names(results: Iterable[CompressionResult]) -> list[CompressionResult]:
    seen: dict[str, int] = {}
    updated: list[CompressionResult] = []
    for result in results:
        count = seen.get(result.filename, 0)
        if count == 0:
            seen[result.filename] = 1
            updated.append(result)
            continue
        stem = Path(result.filename).stem
        suffix = Path(result.filename).suffix
        new_name = f"{stem}-{count + 1}{suffix}"
        seen[result.filename] = count + 1
        updated.append(
            CompressionResult(
                filename=new_name,
                original_size=result.original_size,
                compressed_size=result.compressed_size,
                data=result.data,
                used_original=result.used_original,
            )
        )
    return updated


st.set_page_config(page_title="PDF Compressor", page_icon="🗜️", layout="centered")
st.title("PDF Compressor")
st.write(
    "Compress PDFs in your browser. This app uses lossless stream compression and "
    "can optionally remove metadata. Upload one or more PDFs to get started."
)

with st.sidebar:
    st.subheader("Options")
    remove_metadata = st.checkbox("Remove document metadata", value=True)
    keep_smaller_only = st.checkbox(
        "Keep original if compression increases size",
        value=True,
    )
    output_suffix = st.text_input("Output filename suffix", value="-compressed")
    password = st.text_input(
        "Password (only if the PDF is protected)",
        type="password",
        placeholder="Leave blank if not needed",
    )

uploaded_files = st.file_uploader(
    "Upload PDF files",
    type=["pdf"],
    accept_multiple_files=True,
)

if uploaded_files:
    results: list[CompressionResult] = []
    errors: list[str] = []

    for uploaded_file in uploaded_files:
        try:
            original_bytes = uploaded_file.getvalue()
            compressed_bytes = compress_pdf(
                original_bytes,
                password=password or None,
                remove_metadata=remove_metadata,
            )
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
                )
            )
        except Exception as exc:  # pragma: no cover - Streamlit surfaces the error
            errors.append(f"{uploaded_file.name}: {exc}")

    if errors:
        st.error("Some files could not be processed:")
        for message in errors:
            st.write(f"- {message}")

    if results:
        results = dedupe_names(results)
        st.subheader("Results")
        for result in results:
            ratio = (
                0.0
                if result.original_size == 0
                else (1 - result.compressed_size / result.original_size) * 100
            )
            status_note = " (kept original)" if result.used_original else ""
            st.write(
                f"**{result.filename}** — "
                f"{format_size(result.original_size)} → {format_size(result.compressed_size)} "
                f"({ratio:.1f}% reduction){status_note}"
            )
            st.download_button(
                label=f"Download {result.filename}",
                data=result.data,
                file_name=result.filename,
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
