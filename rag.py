import re
from pathlib import Path
import json
import numpy as np
import voyageai
import time
from dotenv import load_dotenv
from db import pool

load_dotenv()
vo = voyageai.Client()   # reads VOYAGE_API_KEY from the environment

EMBED_MODEL = "voyage-3.5"
HELP_CENTER_DIR = Path(__file__).parent / "data" / "help_center"
INDEX_PATH = Path(__file__).parent / "data" / "help_center_index.json"

def make_chunk(path: Path, title: str, section: str, lines: list[str]) -> dict:
    body = "\n".join(lines).strip()
    return {
        "id": f"{path.stem}#{slugify(section)}",
        "article": title,
        "section": section,
        "source": path.name,
        "text": f"{title} > {section}\n{body}",
    }


def slugify(text: str) -> str:
    """'Pending charges' -> 'pending-charges'"""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def load_chunks() -> list[dict]:
    """Split every help center article into one chunk per '## ' section."""
    chunks = []
    for path in sorted(HELP_CENTER_DIR.glob("*.md")):
        lines = path.read_text(encoding="utf-8").splitlines()
        # TODO 1: find the article title (the line starting with "# ")
        for line in lines:
            if line.startswith("# "):
                title = line[2:].strip()
                break
        # TODO 2: go through the lines. Each "## " line starts a new section,
        #         and the lines after it, up to the next "## ", are its body.
        section_title = None
        section_body = []
        for line in lines:
            if line.startswith("## "):
                if section_title is None:
                    section_title = line[3:].strip()
                    section_body = []
                else:
                    chunks.append(make_chunk(path, title, section_title, section_body))
                    section_title = line[3:].strip()
                    section_body = []

            elif section_title is not None:
                section_body.append(line)
                
            
        # TODO 3: for each section, append a chunk dictionary (shape below)
        if section_title is not None:
            chunks.append(make_chunk(path, title, section_title, section_body))
    return chunks

def build_index() -> None:
    """Embed every chunk once and save the results. Rerun whenever the articles change."""
    chunks = load_chunks()
    if not chunks:
        raise ValueError(f"No help center articles found in {HELP_CENTER_DIR}")
    result = vo.embed([c["text"] for c in chunks], model=EMBED_MODEL, input_type="document")
    print(len(result.embeddings), "embeddings, each with", len(result.embeddings[0]), "numbers")
    
    for chunk, embedding in zip(chunks, result.embeddings):
        chunk["embedding"] = embedding
   
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)
    print(f"Indexed {len(chunks)} chunks")



def top_matches(query_embedding: list[float], k: int) -> list[dict]:
    """The k help center chunks closest to the query embedding, best first, with a similarity score."""
    q = np.array(query_embedding)  # pgvector's adapter sends numpy arrays as vectors
    with pool.connection() as conn:
        return conn.execute(
            """
            SELECT id, article, section, source, text, 1 - (embedding <=> %s) AS score
            FROM help_center_chunks
            ORDER BY embedding <=> %s
            LIMIT %s
            """,
            (q, q, k),
        ).fetchall()


def search(query: str, k: int = 3) -> list[dict]:
    """Return the k chunks closest in meaning to the query, best first."""
    query_embedding = vo.embed([query], model=EMBED_MODEL, input_type="query").embeddings[0]
    return top_matches(query_embedding, k)


if __name__ == "__main__":
    if not INDEX_PATH.exists():      # only embed the articles if there's no saved index yet
        build_index()
    for q in ["someone took my debit card",
              "how long do I have to dispute a charge",
              "can you waive my overdraft fee",
              "what's your phone number"]:
        print(f"\n{q}")
        for r in search(q):
            print(f"  {r['score']:.3f}  {r['id']}")
        time.sleep(21)               # stay under 3 requests per minute