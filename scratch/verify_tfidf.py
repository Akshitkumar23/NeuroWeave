import asyncio
import os
import sys
import math

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from memory.vector_store import PureVectorStore

async def verify_tfidf():
    print("--- VERIFYING PROPER TF-IDF ALGORITHM ---")
    store = PureVectorStore("storage/verify_tfidf_store.json")
    # Clean previous
    store.documents = []
    store.save()

    # Documents designed to test IDF:
    # "the" is a stopword and is ignored.
    # "cagr" appears in doc1 and doc2 (common)
    # "unicorn" appears only in doc2 (rare)
    # "agriculture" appears only in doc1 (rare)
    await store.add_document("Agriculture growth trends and cagr values in India.", {"source": "doc1"})
    await store.add_document("Unicorn startups show huge cagr.", {"source": "doc2"})

    # Query with a rare word "agriculture" and a common word "cagr"
    # Document 1 contains both, but because "agriculture" is rare, it should rank extremely high.
    matches_1 = await store.similarity_search("agriculture", top_k=2)
    print("\nSearch results for 'agriculture':")
    for m in matches_1:
        print(f" - {m['metadata']['source']}: Score = {m['score']:.4f} (Text: '{m['text']}')")

    # Query with "unicorn cagr"
    matches_2 = await store.similarity_search("unicorn cagr", top_k=2)
    print("\nSearch results for 'unicorn cagr':")
    for m in matches_2:
        print(f" - {m['metadata']['source']}: Score = {m['score']:.4f} (Text: '{m['text']}')")

    # Clean up
    if os.path.exists("storage/verify_tfidf_store.json"):
        os.remove("storage/verify_tfidf_store.json")
    print("\nVerification complete!")

if __name__ == "__main__":
    asyncio.run(verify_tfidf())
