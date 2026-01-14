#!/usr/bin/env python3
from zeep import Client

WSDL = "https://tools.rki.de/SurvStat/SurvStatWebService.svc?wsdl"

def main():
    client = Client(WSDL)

    service = list(client.wsdl.services.values())[0]
    port = list(service.ports.values())[0]
    binding = port.binding

    print("Service:", service.name)
    print("Port:", port.name)
    print("\n=== Operations & required inputs ===")

    for op_name, op in binding._operations.items():
        try:
            sig = op.input.signature(as_output=False)
        except Exception:
            sig = "(signature unavailable)"
        print(f"\n- {op_name}{sig}")

    print("\n=== client.service methods ===")
    print([m for m in dir(client.service) if not m.startswith("_")])

if __name__ == "__main__":
    main()
