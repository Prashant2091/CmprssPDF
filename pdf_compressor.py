import streamlit as st
import PyPDF2
import io
import base64

def compress_content_stream(content_stream, compression_factor=0.5):
    # Compress the content stream using FlateEncode filter
    compress_stream = io.BytesIO()
    with PyPDF2.filters.FlateEncode(compress_stream, compression_factor=9) as encoder:
        encoder.write(content_stream)

    compressed_content_stream = compress_stream.getvalue()

    if len(compressed_content_stream) >= len(content_stream):
        return content_stream

    return compressed_content_stream

def compress_pdf(uploaded_file, compression_factor=0.5):
    pdf_reader = PyPDF2.PdfFileReader(uploaded_file)
    pdf_writer = PyPDF2.PdfFileWriter()

    for page in pdf_reader.pages:
        compressed_content = compress_content_stream(page['/Contents'].get_object(), compression_factor)
        page.compressContentStreams()
        page.__setitem__('/Contents', PyPDF2.generic.ByteStringObject(compressed_content))
        pdf_writer.add_page(page)

    pdf_bytes = io.BytesIO()
    pdf_writer.write(pdf_bytes)
    return pdf_bytes

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





