import sys
import json
from src.retriever import ChromaRetriever

def main():
    if len(sys.argv) < 2:
        print("Usage: python get_chunk.py <chunk_id_1> [<chunk_id_2> ...]")
        sys.exit(1)
        
    chunk_ids = sys.argv[1:]
    retriever = ChromaRetriever()
    
    result = retriever._collection.get(ids=chunk_ids)
    
    if not result or not result.get("ids"):
        print(f"No chunks found for IDs: {chunk_ids}")
        return
        
    for i, cid in enumerate(result["ids"]):
        print(f"--- Chunk ID: {cid} ---")
        if result.get("metadatas") and result["metadatas"][i]:
            print(f"Metadata: {json.dumps(result['metadatas'][i], indent=2)}")
        if result.get("documents") and result["documents"][i]:
            print("Content:")
            print(result["documents"][i])
        print("-" * 40 + "\n")

if __name__ == "__main__":
    main()
