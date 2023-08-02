import streamlit as st
import PyPDF2
import io
import img2pdf
import subprocess

def compress_pdf(input_file, compression_factor):
    # Convert the PDF pages to images and compress them using ImageMagick
    images = []
    reader = PyPDF2.PdfFileReader(input_file)
    temp_files = []

    for page_number in range(reader.numPages):
        page = reader.getPage(page_number)
        pdf_page_bytes = io.BytesIO()
        pdf_writer = PyPDF2.PdfFileWriter()
        pdf_writer.addPage(page)
        pdf_writer.write(pdf_page_bytes)
        pdf_page_bytes.seek(0)

        image_file = io.BytesIO()
        subprocess.run(['convert', '-density', '300', '-', '-quality', str(compression_factor * 100), 'JPEG:-'],
                       input=pdf_page_bytes.read(), stdout=image_file, check=True, text=True)
        image_file.seek(0)

        temp_files.append(image_file)
        images.append(image_file)

    # Create a PDF from the compressed images
    compressed_pdf_bytes = io.BytesIO()
    img2pdf.convert(images, outputstream=compressed_pdf_bytes)
    compressed_pdf_bytes.seek(0)

    # Close the temporary image files
    for temp_file in temp_files:
        temp_file.close()

    return compressed_pdf_bytes

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
