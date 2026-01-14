#!/usr/bin/env python3
from zeep import Client

WSDL = "https://tools.rki.de/SurvStat/SurvStatWebService.svc?wsdl"

def main():
    client = Client(WSDL)

    # Find available measures (these often represent diseases or case counts)
    print("=== MEASURES ===")
    measures = client.service.GetAllMeasures()
    for m in measures:
        # Print compactly
        print(f"{m['Id']} | {m['Name']}")

    print("\n=== DIMENSIONS ===")
    dims = client.service.GetAllDimensions()
    for d in dims:
        print(f"{d['Id']} | {d['Name']}")

if __name__ == "__main__":
    main()
