import os
import streamlit as st
from langchain_ollama import OllamaEmbeddings, OllamaLLM
import chromadb
import pandas as pd
import fitz  # PyMuPDF для работы с PDF
from docx import Document
import logging

# Конфигурация
llm_model = "llama3.2"
base_url = "http://localhost:11434"  # Настройте URL для вашего Ollama-сервера

# Инициализация ChromaDB клиента
chroma_client = chromadb.PersistentClient(path=os.path.join(os.getcwd(), "chroma_db"))

# Логирование
logging.basicConfig(filename="query_logs.log", level=logging.INFO)

# Пользовательская функция эмбеддингов для ChromaDB
class ChromaDBEmbeddingFunction:
    def init(self, langchain_embeddings):
        self.langchain_embeddings = langchain_embeddings

    def call(self, input):
        if isinstance(input, str):
            input = [input]
        return self.langchain_embeddings.embed_documents(input)

# Инициализация функции эмбеддингов
embedding = ChromaDBEmbeddingFunction(
    OllamaEmbeddings(model=llm_model, base_url=base_url)
)

# Создание или получение коллекции
collection_name = "constitution_collection"
constitution_collection = chroma_client.get_or_create_collection(
    name=collection_name,
    metadata={"description": "Коллекция Конституции Казахстана"},
    embedding_function=embedding
)

# Функция для добавления документов в коллекцию
def add_documents_to_collection(collection, documents, ids):
    collection.add(documents=documents, ids=ids)

# Функция для обработки текста Конституции
def preprocess_constitution(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    articles = content.split("Article")
    preprocessed = {f"Article {i}": text.strip() for i, text in enumerate(articles, 1) if text.strip()}
    return preprocessed

# Функция для выполнения запроса к ChromaDB
def query_chromadb(collection, query_text, n_results=3):
    results = collection.query(
        query_texts=[query_text],
        n_results=n_results
    )

    # Отладочный вывод для проверки структуры метаданных
    print("Результаты запроса к ChromaDB:", results)

    return results["documents"], results["metadatas"]

# Функция взаимодействия с Ollama LLM
def query_ollama(prompt):
    llm = OllamaLLM(model=llm_model, base_url=base_url)
    return llm.stream(prompt)

# Основной конвейер RAG
def rag_pipeline(query_text):
    retrieved_docs, metadata = query_chromadb(constitution_collection, query_text)

    context = "\n\n".join(retrieved_docs[0]) if retrieved_docs else "Релевантные документы не найдены."

    # Обработка метаданных
    if metadata and isinstance(metadata, list) and all(isinstance(meta, dict) for meta in metadata):
        articles = ", ".join(meta.get("id", "N/A") for meta in metadata)

    augmented_prompt = f"Контекст: {context}\n\nВопрос: {query_text}\n\nОтвет с указанием статей:"
    response = query_ollama(augmented_prompt)

    # Собрать весь текст из генератора
    full_response = "".join(response)
    
    return full_response + f"\n\nУпомянутые статьи: {articles}"

# Интерфейс Streamlit
st.title("Чат-бот по Конституции Казахстана")

# Предзагрузка Конституции
constitution_file_path = "constitution_kazakhstan.txt"
if os.path.exists(constitution_file_path):
    st.info("Загрузка текста Конституции...")
    constitution_content = preprocess_constitution(constitution_file_path)
    for article, content in constitution_content.items():
        add_documents_to_collection(constitution_collection, [content], [article])
    st.success("Текст Конституции успешно загружен!")

# Загрузка пользовательских документов
uploaded_files = st.file_uploader(
    "Загрузите ваши документы (.txt, .pdf, .docx, .csv)", 
    type=["txt", "pdf", "docx", "csv"], 
    accept_multiple_files=True
)

if uploaded_files:
    for uploaded_file in uploaded_files:
        file_id = uploaded_file.name