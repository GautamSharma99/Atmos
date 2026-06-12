from dotenv import load_dotenv
import os
import psycopg

load_dotenv()

conn = psycopg.connect(
    host=os.getenv("DB_HOST"),
    port=os.getenv("DB_PORT"),
    dbname=os.getenv("DB_NAME"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD")
)

cur = conn.cursor()

cur.execute("SELECT * FROM aqi_data")

rows = cur.fetchall()

for row in rows:
    print(row)

cur.close()
conn.close()