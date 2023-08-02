import streamlit as st
import PyPDF2

# Function to compress the PDF
def compress_pdf(uploaded_file, compression_factor):
    input_pdf = PyPDF2.PdfFileReader(uploaded_file)

    # Create a new PDF with compression settings
    output_pdf = PyPDF2.PdfFileWriter()
    for page_number in range(input_pdf.getNumPages()):
        page = input_pdf.getPage(page_number)
        page.compressContentStreams(compression_factor)
        output_pdf.addPage(page)

    return output_pdf

# Streamlit app title
st.title('PDF Compressor')

# File uploader widget
uploaded_file = st.file_uploader("Upload a PDF file", type=["pdf"])

# Compression factor slider
compression_factor = st.slider("Compression Factor", min_value=0, max_value=9, step=1, value=0)

if uploaded_file is not None:
    # Display the uploaded file
    st.write(f"Original File Size: {round(uploaded_file.size/1024, 2)} KB")

    # Compress the PDF
    compressed_pdf = compress_pdf(uploaded_file, compression_factor)

    # Save the compressed PDF to a buffer
    output_buffer = BytesIO()
    compressed_pdf.write(output_buffer)

    # Download button to download the compressed PDF
    st.download_button(label="Download Compressed PDF", data=output_buffer.getvalue(), file_name="compressed_pdf.pdf")

    # Display the compressed file size
    st.write(f"Compressed File Size: {round(len(output_buffer.getvalue())/1024, 2)} KB")
