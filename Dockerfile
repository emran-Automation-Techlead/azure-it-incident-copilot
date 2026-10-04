FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN sed -i 's/\r$//' start.sh && chmod +x start.sh
EXPOSE 8000 8501
CMD ["./start.sh"]
