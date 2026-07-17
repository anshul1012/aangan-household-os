FROM python:3.12-slim

# Run as non-root inside the container.
RUN useradd --create-home aangan
WORKDIR /home/aangan/app

COPY requirements.txt .
# Upgrade pip first: the pip bundled in python:3.12-slim backtracks badly through
# google-genai's deep dependency tree with our loose upper bounds, and can fail
# with a misleading ResolutionImpossible. A current pip resolves these instantly.
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

COPY aangan/ aangan/
COPY db/ db/
COPY main.py .

USER aangan

CMD ["python", "main.py"]
