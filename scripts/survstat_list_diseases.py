#!/usr/bin/env python3
from zeep import Client

WSDL = "https://tools.rki.de/SurvStat/SurvStatWebService.svc?wsdl"
CUBE_ID = "SurvStat"  # this is the standard cube used by the UI

def main():
    client = Client(WSDL)

    print("=== Hierarchies ===")
    hierarchies = client.service.GetAllHierarchies({
        "CubeId": CUBE_ID
    })

    disease_hierarchy_id = None

    for h in hierarchies:
        hid = h["Id"]
        name = h["Name"]
        print(f"{hid} | {name}")

        # Heuristic: German UI uses Meldetatbestand / Krankheit
        if "krank" in name.lower() or "melde" in name.lower():
            disease_hierarchy_id = hid

    if not disease_hierarchy_id:
        print("\n❌ Could not auto-detect disease hierarchy.")
        print("Pick one manually from the list above.")
        return

    print(f"\n=== Diseases (Hierarchy: {disease_hierarchy_id}) ===")

    members = client.service.GetAllHierarchyMembers({
        "CubeId": CUBE_ID,
        "HierarchyId": disease_hierarchy_id
    })

    for m in members:
        print(f"{m['Id']} | {m['Name']}")

    print(f"\nTotal diseases found: {len(members)}")

if __name__ == "__main__":
    main()
