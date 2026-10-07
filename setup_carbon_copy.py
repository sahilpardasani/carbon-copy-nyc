from carbon_copy import INDEX_NAME, elastic_client, ensure_data


if __name__ == "__main__":
    es = elastic_client()
    info = es.info()
    count = ensure_data(es)
    print(f"Connected to Elasticsearch {info['version']['number']}")
    print(f"Indexed {count:,} NYC buildings in {INDEX_NAME}")
