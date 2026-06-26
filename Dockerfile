FROM python:3.12-slim

# Run as non-root inside the container.
RUN useradd --create-home aangan
WORKDIR /home/aangan/app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY aangan/ aangan/
COPY main.py .

USER aangan

CMD ["python", "main.py"]
