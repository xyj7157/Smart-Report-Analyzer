import os
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
os.environ["HF_HUB_OFFLINE"] = "1"



from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_milvus import Milvus

MILVUS_URI = "http://localhost:19530"


def build_kb():
    print("1. 正在加载合规文档...")
    loader = TextLoader("core/compliance.txt", encoding="utf-8")
    docs = loader.load()

    print("2. 正在切分文本...")
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=200, chunk_overlap=30)
    splits = text_splitter.split_documents(docs)

    print("3. 正在向量化并存入 Milvus（首次运行需下载模型，请耐心等待）...")
    # 使用本地中文向量模型
    embeddings = HuggingFaceEmbeddings(model_name="BAAI/bge-small-zh-v1.5")

    # 存入 Milvus
    Milvus.from_documents(
        documents=splits,
        embedding=embeddings,
        collection_name="compliance_rules",
        connection_args={"uri": MILVUS_URI},
    )
    print("✅ 知识库已成功存入 Milvus！")


if __name__ == "__main__":
    build_kb()