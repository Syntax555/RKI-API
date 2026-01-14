#!/usr/bin/env python3
import sys

def main():
    try:
        import zeep
    except Exception:
        print("Missing dependency 'zeep'. Install with: pip install zeep", file=sys.stderr)
        sys.exit(1)

    wsdl = "https://tools.rki.de/SurvStat/SurvStatWebService.svc?wsdl"
    client = zeep.Client(wsdl=wsdl)

    # Print service + operations so we can see what SurvStat exposes
    print("SurvStat WSDL loaded.")
    for service in client.wsdl.services.values():
        print("Service:", service.name)
        for port in service.ports.values():
            print(" Port:", port.name)
            operations = sorted(port.binding._operations.keys())
            print("  Operations:", operations)

    # Many SOAP services expose something like GetAllHierarchies().
    # We try it, but do not crash if it's different.
    for op_name in ["GetAllHierarchies", "GetHierarchies", "GetAllDimensions"]:
        if hasattr(client.service, op_name):
            print(f"\nTrying operation: {op_name}()")
            try:
                res = getattr(client.service, op_name)()
                # Print a small preview
                print("Result type:", type(res))
                print("Preview:", str(res)[:800])
            except Exception as e:
                print("Call failed:", repr(e))
            break
    else:
        print("\nNo known hierarchy operation found. Check printed operations and tell me the names.")

if __name__ == "__main__":
    main()
