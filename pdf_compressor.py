import streamlit as st
import PyPDF2

# Function to compress the PDF
def compress_pdf(input_file, compression_factor):
    output_file = f"compressed_pdf_{compression_factor}.pdf"

    with open(input_file, "rb") as file:
        reader = PyPDF2.PdfFileReader(file)
        writer = PyPDF2.PdfFileWriter()

        for page_num in range(reader.getNumPages()):
            page = reader.getPage(page_num)
            page.compressContentStreams(compression_factor)
            writer.addPage(page)

        with open(output_file, "wb") as output:
            writer.write(output)

    return output_file

# Streamlit app title
st.title("PDF Compressor")

# File uploader widget
uploaded_file = st.file_uploader("Upload a PDF file", type=["pdf"])

if uploaded_file is not None:
    st.write("Original File Size:", round(uploaded_file.size / 1024, 2), "KB")

    # Compression factor slider
    compression_factor = st.slider("Select Compression Factor", min_value=0, max_value=9, value=4)

    # Compress the PDF and get the compressed file name
    compressed_file = compress_pdf(uploaded_file, compression_factor)

    st.write("Download Compressed PDF")
    st.markdown(f'<a href="data:application/pdf;base64,{compressed_file}">Click here to download</a>', unsafe_allow_html=True)

    st.write("Compressed File Size:", round(compressed_file.size / 1024, 2), "KB")
