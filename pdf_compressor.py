Copy code
import streamlit as st
import base64
import PyPDF4

# Function to compress the PDF
def compress_pdf(uploaded_file, compression_factor):
    output_buffer = BytesIO()

    pdf_reader = PyPDF4.PdfReader(uploaded_file)
    pdf_writer = PyPDF4.PdfWriter()

    for page_number in range(len(pdf_reader.pages)):
        page = pdf_reader.pages[page_number]

        # Get the compressed PDF page
        compressed_page = pdf_writer.add_blank_page(
            width=page.mediaBox.getWidth(), height=page.mediaBox.getHeight()
        )
        compressed_page.merge_page(page)

        # Compressing the image with the specified compression factor
        xObject = compressed_page["/Resources"]["/XObject"].get_object()
        for obj in xObject:
            if xObject[obj]["/Subtype"] == "/Image":
                xObject[obj].update({
                    PyPDF4.generic.NameObject("/Filter"): PyPDF4.generic.NameObject("/FlateDecode"),
                    PyPDF4.generic.NameObject("/Q"): PyPDF4.generic.createStringObject(str(compression_factor))
                })

    pdf_writer.write(output_buffer)
    pdf_writer.close()

    return output_buffer

# Streamlit app title
st.title('PDF Compressor')

# File uploader widget
uploaded_file = st.file_uploader("Upload a PDF file", type=["pdf"])

# Compression factor slider
compression_factor = st.slider("Compression Factor", min_value=10, max_value=100, step=10, value=50)

if uploaded_file is not None:
    # Display the original file size
    original_size_kb = round(uploaded_file.size / 1024, 2)
    st.write(f"Original File Size: {original_size_kb} KB")

    # Compress the PDF
    compressed_buffer = compress_pdf(uploaded_file, compression_factor)

    # Convert buffer to base64
    encoded_pdf = base64.b64encode(compressed_buffer.getvalue()).decode()

    # Download link to download the compressed PDF
    st.markdown(f'<a href="data:application/pdf;base64,{encoded_pdf}" download="compressed_pdf.pdf">Download Compressed PDF</a>', unsafe_allow_html=True)

    # Display the compressed file size
    compressed_size_kb = round(len(compressed_buffer.getvalue()) / 1024, 2)
    st.write(f"Compressed File Size: {compressed_size_kb} KB")
