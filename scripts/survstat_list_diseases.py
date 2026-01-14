#!/usr/bin/env python3
from zeep import Client

WSDL = "https://tools.rki.de/SurvStat/SurvStatWebService.svc?wsdl"

def main():
    client = Client(WSDL)

    # Properly constructed request object
    hierarchy_request = {
        "CubeId": "SurvStat",
        "Language": "de"
    }

    print("=== Hierarchies ===")
    hierarchies = client.service.GetAllHierarchies(hierarchy_request)

    disease_hierarchy_id = None

    for h in hierarchies:
        hid = h["Id"]
        name = h["Name"]
        print(f"{hid} | {name}")

        if "krank" in name.lower() or "melde" in name.lower():
            disease_hierarchy_id = hid

    if not disease_hierarchy_id:
        print("\n❌ No disease hierarchy auto-detected.")
        print("Pick one manually from the list above.")
        return

    print(f"\n=== Diseases (Hierarchy: {disease_hierarchy_id}) ===")

    member_request = {
        "CubeId": "SurvStat",
        "HierarchyId": disease_hierarchy_id,
        "Language": "de"
    }

    members = client.service.GetAllHierarchyMembers(member_request)

    for m in members:
        print(f"{m['Id']} | {m['Name']}")

    print(f"\nTotal diseases found: {len(members)}")

if __name__ == "__main__":
    main()
