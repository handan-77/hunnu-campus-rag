import os
import jsonlines
import chromadb
from sentence_transformers import SentenceTransformer

# -------------------------- 全局配置（无需修改） --------------------------
# 轻量级多语言模型（支持中文，384 维，体积小、云端部署快）
LOCAL_MODEL_PATH = "./models/paraphrase-multilingual-MiniLM-L12-v2"
# 云端部署（无本地模型目录）时自动从 HuggingFace Hub 下载
MODEL_PATH = LOCAL_MODEL_PATH if os.path.isdir(LOCAL_MODEL_PATH) else "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
INPUT_VECTOR_FILE = "rag_output/chunk_with_vector.jsonl"
CHROMA_DB_PATH = "./db"
COLLECTION_NAME = "hunnu_school_knowledge"
SIM_THRESHOLD = 0.0  # 低于该相似度直接过滤

# 加载嵌入模型（本地离线优先，云端自动下载）
print(f"加载嵌入模型 paraphrase-multilingual-MiniLM-L12-v2（{MODEL_PATH}）...")
bge_model = SentenceTransformer(MODEL_PATH)

# 初始化向量库客户端，指定余弦距离空间
client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
# 创建/获取集合，使用余弦相似度
collection = client.get_or_create_collection(
    name=COLLECTION_NAME,
    metadata={"hnsw:space": "cosine"}
)


# 批量入库函数（修复获取已有ID的报错，移除collection.get取ids逻辑）
def load_all_chunk_to_chroma():
    batch_ids = []
    batch_embeddings = []
    batch_docs = []
    batch_meta = []
    total_count = 0

    print("===== 开始读取向量文件并批量入库 =====")
    with jsonlines.open(INPUT_VECTOR_FILE, "r") as reader:
        for item in reader:
            total_count += 1
            current_id = f"id_{total_count}"

            batch_ids.append(current_id)
            batch_embeddings.append(item["embedding"])
            batch_docs.append(item["chunk_text"])
            meta_info = {
                "title": item["source_title"],
                "source_url": item.get("source_url", "")
            }
            batch_meta.append(meta_info)

            # 满500条执行一次入库
            if len(batch_ids) >= 500:
                collection.add(
                    ids=batch_ids,
                    embeddings=batch_embeddings,
                    documents=batch_docs,
                    metadatas=batch_meta
                )
                print(f"已完成入库 {total_count} 条分片")
                batch_ids.clear()
                batch_embeddings.clear()
                batch_docs.clear()
                batch_meta.clear()
        # 写入最后不足500条的剩余数据
        if len(batch_ids) > 0:
            collection.add(
                ids=batch_ids,
                embeddings=batch_embeddings,
                documents=batch_docs,
                metadatas=batch_meta
            )
    final_total = collection.count()
    print(f"\n✅ 入库操作结束！库内现有总数据量：{final_total} 条")


# 检索测试：手动BGE编码，内置相似度过滤，只输出高匹配片段
def search_test(query: str, top_k: int = 5):
    print(f"🔍 检索：{query}")
    query_vec = bge_model.encode(query, normalize_embeddings=True).tolist()
    result = collection.query(
        query_embeddings=[query_vec],
        n_results=top_k,
        include=["documents", "metadatas", "distances"]
    )
    docs = result["documents"][0]
    metas = result["metadatas"][0]
    dists = result["distances"][0]
    
    results = []
    for idx in range(len(docs)):
        cos_sim = 1 - dists[idx]
        if cos_sim < SIM_THRESHOLD:
            continue
        results.append({
            "content": docs[idx],
            "title": metas[idx]["title"],
            "score": cos_sim,
            "source_url": metas[idx].get("source_url", "")  # 官网原文链接（溯源跳转用）
        })
    
    print(f"   → 找到 {len(results)} 条高匹配结果")
    return results  # ← 关键：返回结果，而不是打印

if __name__ == "__main__":
    # 前置强制操作：删除旧 rag_vector_db 文件夹
    # 第一次全新入库取消注释，入库完成后注释此行
    #load_all_chunk_to_chroma()

    # 执行离线检索测试
    search_test("廉洁文化")