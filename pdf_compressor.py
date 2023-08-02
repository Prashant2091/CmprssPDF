import streamlit as st
import PyPDF2
import io
import base64

def compress_pdf(uploaded_file, compression_factor=0.5):
    pdf_reader = PyPDF2.PdfFileReader(uploaded_file)
    pdf_writer = PyPDF2.PdfFileWriter()

    for page in pdf_reader.pages:
        pdf_writer.add_page(page)

    compressed_pdf = io.BytesIO()
    pdf_writer.write(compressed_pdf)
    compressed_pdf.seek(0)

    return compressed_pdf

def main():
    st.title("PDF Compressor")

    uploaded_file = st.file_uploader("Upload a PDF file", type=["pdf"])
    if uploaded_file:
        compression_factor = st.slider("Compression Factor", 0.0, 1.0, 0.5, 0.01)

        if st.button("Compress"):
            compressed_pdf = compress_pdf(uploaded_file, compression_factore)

            st.markdown(
                f'<a href="data:application/pdf;base64,{base64.b64encode(compressed_pdf.getvalue()).decode()}" download="compressed.pdf">Download Compressed PDF</a>',
                unsafe_allow_html=True
            )

if __name__ == "__main__":
    main()
