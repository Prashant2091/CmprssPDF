import streamlit as st
import base64
import PyPDF2
import io

def compress_pdf(input_file, compression_factor=0.5):
    pdf_reader = PyPDF2.PdfFileReader(input_file)
    compressed_pdf = io.BytesIO()
    pdf_writer = PyPDF2.PdfFileWriter()

    for page in pdf_reader.pages:
        compressed_page = page.compress(compression_factor)
        pdf_writer.add_page(compressed_page)

    pdf_writer.write(compressed_pdf)
    compressed_pdf.seek(0)
    return compressed_pdf

def main():
    st.title("PDF Compressor")

    uploaded_file = st.file_uploader("Upload a PDF file", type=["pdf"])
    if uploaded_file:
        compression_factor = st.slider("Select Compression Factor", min_value=0.1, max_value=1.0, step=0.1, value=0.5)

        if st.button("Compress PDF"):
            compressed_pdf = compress_pdf(uploaded_file, compression_factor)

            st.markdown(f'<a href="data:application/pdf;base64,{base64.b64encode(compressed_pdf.getvalue()).decode()}" download="compressed.pdf">Download Compressed PDF</a>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()
