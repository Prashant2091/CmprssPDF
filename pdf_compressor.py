import streamlit as st
import PyPDF2
import io

def compress_pdf(input_file, compression_factor):
    reader = PyPDF2.PdfFileReader(input_file)
    writer = PyPDF2.PdfFileWriter()

    for page_number in range(reader.numPages):
        page = reader.getPage(page_number)
        # Reduce the resolution to reduce file size
        page.compressContentStreams(compression_factor)
        writer.addPage(page)

    output_buffer = io.BytesIO()
    writer.write(output_buffer)
    output_buffer.seek(0)
    return output_buffer

st.title("PDF Compressor")

# File uploader widget
uploaded_file = st.file_uploader("Upload a PDF file", type=["pdf"])

if uploaded_file is not None:
    # Display the original file size
    original_size = round(len(uploaded_file.read()) / 1024, 2)  # Convert to KB
    st.write(f"Original File Size: {original_size} KB")

    # Slider for compression factor
    compression_factor = st.slider("Select Compression Factor", min_value=0.1, max_value=1.0, step=0.1, value=0.5)

    # Compress the PDF file
    compressed_file = compress_pdf(uploaded_file, compression_factor)

    # Display the compressed file size
    compressed_size = round(len(compressed_file.getvalue()) / 1024, 2)  # Convert to KB
    st.write(f"Download Compressed PDF (Compression Factor: {compression_factor:.1f})")
    st.download_button(
        label=f"Compressed File Size: {compressed_size} KB",
        data=compressed_file.getvalue(),
        file_name="compressed.pdf",
    )
