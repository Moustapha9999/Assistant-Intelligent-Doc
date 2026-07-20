"""Script de diagnostic RAGAS — à supprimer après debug."""
import os
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")


from ragas.metrics import Faithfulness  
from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.dataset_schema import SingleTurnSample
from langchain_groq import ChatGroq
from langchain_huggingface import HuggingFaceEmbeddings

base_dir = Path(__file__).resolve().parent.parent.parent
fichier = base_dir / "resultats" / "generation" / "reponses_generees.json"

with open(fichier, encoding="utf-8") as f:
    d = json.load(f)["donnees"][0]

llm = LangchainLLMWrapper(ChatGroq(
    api_key=os.getenv("GROQ_API_KEY"),
    model=os.getenv("LLM_MODEL", "llama-3.3-70b-versatile"),
    temperature=0.0,
    max_tokens=2048,
))
emb = LangchainEmbeddingsWrapper(HuggingFaceEmbeddings(
    model_name="all-MiniLM-L6-v2",
    cache_folder=str(base_dir / "models_cache"),
))

# Test avec réponse tronquée vs complète
for label, reponse in [("tronquee", d["reponse_generee"][:1500]), ("complete", d["reponse_generee"])]:
    sample = SingleTurnSample(
        user_input=d["question"],
        response=reponse,
        retrieved_contexts=d["contextes"][:3],
        reference=d["reponse_ideale"],
    )
    metric = Faithfulness(llm=llm)
    try:
        score = metric.single_turn_score(sample)
        print(f"{label}: faithfulness = {score}")
    except Exception as e:
        print(f"{label}: ERREUR = {type(e).__name__}: {e}")
