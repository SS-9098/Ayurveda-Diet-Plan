FROM python:3.12.3

RUN apt-get update && apt-get install -y --no-install-recommends build-essential curl ca-certificates git && rm -rf /var/lib/apt/lists/*

#RUN curl https://sh.rustup.rs -sSf | sh -s -- -y
#ENV PATH="/root/.cargo/bin:${PATH}"

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p output

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4", "--loop", "uvloop"]