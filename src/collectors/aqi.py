from datetime import datetime

from src.database.connection import get_connection
from src.schemas.aqi import AQIRecord


def fetch_aqi():
    return {
        "station_id": "BLR001",
        "timestamp": datetime.now(),
        "pm25": 48.2,
        "pm10": 82.4,
        "aqi": 118
    }


def save_aqi(record: AQIRecord):
    conn = get_connection()

    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO aqi_data
        (station_id, timestamp, pm25, pm10, aqi)
        VALUES (%s,%s,%s,%s,%s)
        """,
        (
            record.station_id,
            record.timestamp,
            record.pm25,
            record.pm10,
            record.aqi
        )
    )

    conn.commit()

    cur.close()
    conn.close()


def main():
    raw_data = fetch_aqi()

    record = AQIRecord(**raw_data)

    save_aqi(record)

    print("AQI record saved")


if __name__ == "__main__":
    main()