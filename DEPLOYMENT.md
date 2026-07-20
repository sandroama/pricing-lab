# Deployment — pricing-lab

This project is **CPU-only**, has no model downloads, and ships in <50 MB.

## Hugging Face Spaces (recommended)

The Space needs the whole project tree (`hf_space/app.py` runs
`dashboard/app.py` with `src/` on `sys.path`), plus `hf_space/README.md`,
`hf_space/app.py`, and `hf_space/requirements.txt` at the Space repo ROOT:

```bash
# From the project root:
huggingface-cli upload <your-username>/pricing-lab . --repo-type space \
  --exclude ".venv/*" --exclude "data/*" --exclude "**/__pycache__/*"
huggingface-cli upload <your-username>/pricing-lab hf_space/README.md README.md --repo-type space
huggingface-cli upload <your-username>/pricing-lab hf_space/app.py app.py --repo-type space
huggingface-cli upload <your-username>/pricing-lab hf_space/requirements.txt requirements.txt --repo-type space
```

The Spaces config is in `hf_space/README.md` (Streamlit SDK, free CPU
tier, ~30s cold start). `app.py` detects whether it runs from `hf_space/`
or from the Space repo root, so the root-level copy works as-is.

## Streamlit Cloud

1. Push the repo to GitHub.
2. On https://share.streamlit.io, point at this folder; entry point
   `dashboard/app.py`.
3. Add `pricelab` to the install path via `requirements.txt` (the
   pyproject is auto-detected; if needed add `-e .` to a sibling
   `requirements.txt`).

## Local Docker

```bash
# minimal Dockerfile (not committed — write yourself)
FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install -e ".[ui]"
CMD ["streamlit", "run", "dashboard/app.py", "--server.port=8501", "--server.address=0.0.0.0"]
```

```bash
docker build -t pricing-lab . && docker run -p 8501:8501 pricing-lab
```
