import streamlit as st
import PyPDF2
import io
import base64

def compress_pdf(uploaded_file, compression_factor=0.5):
    pdf_reader = PyPDF2.PdfFileReader(uploaded_file)
    pdf_writer = PyPDF2.PdfFileWriter()

    for page_number in range(pdf_reader.getNumPages()):
        page = pdf_reader.getPage(page_number)
        content = page.getContents()
        if not isinstance(content, PyPDF2.pdf.ContentStream):
            content = PyPDF2.pdf.ContentStream(content, pdf_writer)
        for operands, operator in content.operations:
            if operator == b'Tj':
                # Text-showing operators (Tj) represent text content
                operands[0] = PyPDF2.generic.TextStringObject(operands[0].get_object().encode('ascii', 'ignore').decode())
            elif operator == b'TJ':
                # Text-showing operators (TJ) represent array of strings
                operands[0] = PyPDF2.generic.ArrayObject([PyPDF2.generic.TextStringObject(obj.get_object().encode('ascii', 'ignore').decode()) if isinstance(obj, PyPDF2.generic.TextStringObject) else obj for obj in operands[0]])
        page.__setitem__(PyPDF2.generic.NameObject('/Contents'), content)
        page.compressContentStreams()
        pdf_writer.addPage(page)

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
            compressed_pdf = compress_pdf(uploaded_file, compression_factor)
            href = f"data:application/pdf;base64,{base64.b64encode(compressed_pdf.getvalue()).decode()}"
            st.markdown(f'<a href="{href}" download="compressed.pdf">Download Compressed PDF</a>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()
