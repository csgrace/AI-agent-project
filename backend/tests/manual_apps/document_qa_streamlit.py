import streamlit as st

from src.services.document_qa.agent import Agent
from src.services.document_qa.chunker import chunk_text
from src.services.document_qa.loader import load_pdfs
from src.services.document_qa.service import get_document_qa_service

st.title("Student Policy Agent")

if "agent" not in st.session_state:
    docs = load_pdfs()
    chunks = chunk_text(docs)
    get_document_qa_service().set_chunks(chunks)
    st.session_state.agent = Agent()

query = st.text_input("Ask a question:")

if query:
    answer, trace = st.session_state.agent.run(query)

    st.subheader("Answer")
    st.write(answer)

    st.subheader("Thought Trace")
    for item in trace:
        st.write(item)
