import streamlit as st
import PyPDF2
import io
import base64

def compress_pdf(uploaded_file, compression_factor=0.5):
    pdf_reader = PyPDF2.PdfFileReader(uploaded_file)
    pdf_writer = PyPDF2.PdfFileWriter()

    for page_number in range(len(pdf_reader.pages)):
        page = pdf_reader.pages[page_number]
        compressed_page = pdf_writer.add_blank_page(width=page.mediaBox.getWidth(), height=page.mediaBox.getHeight())
        compressed_page.merge_page(page)

    compressed_pdf = io.BytesIO()
    pdf_writer.write(compressed_pdf)
    return compressed_pdf

def main():
    st.title("PDF Compressor")

    uploaded_file = st.file_uploader("Upload a PDF file", type=["pdf"])

    if uploaded_file is not None:
        st.subheader("Original File Size:")
        st.write(f"{uploaded_file.size / 1024:.2f} KB")

        compression_factor = st.slider("Compression Factor", 0.1, 1.0, 0.5, 0.1)

        if st.button("Compress PDF"):
            compressed_pdf = compress_pdf(uploaded_file, compression_factor)

            st.subheader("Compressed File Size:")
            st.write(f"{len(compressed_pdf.getvalue()) / 1024:.2f} KB")

            st.markdown(
                f'<a href="data:application/pdf;base64,{base64.b64encode(compressed_pdf.getvalue()).decode()}" download="compressed.pdf">Download Compressed PDF</a>',
                unsafe_allow_html=True
            )

if __name__ == "__main__":
    main()
