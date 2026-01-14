#!/usr/bin/env python3
from zeep import Client

WSDL = "https://tools.rki.de/SurvStat/SurvStatWebService.svc?wsdl"

def main():
    client = Client(WSDL)

    print("=== CUBES ===")
    cubes = client.service.GetCubeInfo()
    for c in cubes:
        print(f"{c['Id']} | {c['Name']}")

if __name__ == "__main__":
    main()
