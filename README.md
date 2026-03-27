#  RAG Documentation Assistant

Système intelligent d'assistance à la recherche documentaire technique pour développeurs francophones.

##  Description

Ce projet implémente un système RAG (Retrieval Augmented Generation) permettant d'interroger en français la documentation technique open-source de 500 projets GitHub de haute qualité.

##  Objectifs

- Réduire le temps de recherche documentaire de 70%
- Fournir des réponses en français avec citations sources
- Alternative gratuite et open-source aux outils commerciaux

##  Architecture

- Corpus : 500 projets GitHub (Python, JavaScript, Java, C, C++)
- Embeddings : Sentence-Transformers
- Vector DB : Qdrant
- Retrieval : Hybride (Dense + Sparse + Reranking)
- Generation : GPT-4-Turbo
- Interface : Streamlit

##  Performance visée

- Precision@5 > 80%
- Faithfulness > 90%
- Latence < 5s

##  Installation
```bash
# Cloner le repo
git clone https://github.com/Moustapha9999/Assistant-Intelligent-Doc.git
cd Assistant-Intelligent-Doc
# Créer environnement virtuel
python -m venv venv
source venv/bin/activate  # Mac/Linux
# venv\Scripts\activate  # Windows

# Installer les dépendances
pip install -r requirements.txt

# Configurer variables d'environnement
cp .env.example .env
# Éditer .env avec vos clés API
```

##  Usage

(À compléter après développement)

##  Licence

MIT License

##   Auteur

Moustapha Youssouf Sall - Master 2 IAGE - ISI KOMINUK