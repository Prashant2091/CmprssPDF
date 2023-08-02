import streamlit as st
import PyPDF2
import io

def compress_pdf(uploaded_file, compression_factor):
    pdf_reader = PyPDF2.PdfFileReader(uploaded_file)
    pdf_writer = PyPDF2.PdfFileWriter()

    for page_num in range(pdf_reader.numPages):
        page = pdf_reader.getPage(page_num)
        page.scaleBy(compression_factor)
        pdf_writer.addPage(page)

    return pdf_writer

def main():
    st.title("PDF Compressor")
    st.write("Upload a PDF file and choose the compression factor.")

    uploaded_file = st.file_uploader("Upload a PDF file", type=["pdf"])

    if uploaded_file is not None:
        compression_factor = st.slider("Compression Factor", 0.1, 1.0, 0.5, 0.1)

        if st.button("Compress"):
            compressed_pdf = compress_pdf(uploaded_file, compression_factor)

            # Save the compressed PDF to a bytes buffer
            output_buffer = io.BytesIO()
            compressed_pdf.write(output_buffer)
            output_buffer.seek(0)

            # Provide a custom button label and link to trigger download
            st.markdown(
                f'<a href="data:application/pdf;base64,{output_buffer.read().encode("base64").decode()}">Download Compressed PDF</a>',
                unsafe_allow_html=True,
            )

if __name__ == "__main__":
    main()
