"""
data_generator/name_pools.py

Synthetic data pools for the K12 credential data generator.
All names are randomly assembled — any resemblance to real individuals is coincidental.
"""

FIRST_NAMES = [
    "Amara", "Liam", "Sofia", "Noah", "Priya", "Ethan", "Yuki", "Marcus",
    "Aaliyah", "Diego", "Mei", "James", "Fatima", "Oliver", "Zara", "Elijah",
    "Nadia", "Samuel", "Ingrid", "Carlos", "Aisha", "Henry", "Layla", "Jaylen",
    "Chloe", "Andre", "Leila", "Tyler", "Sana", "Jordan", "Hana", "Miles",
    "Yasmin", "Caleb", "Nia", "Owen", "Riya", "Nathan", "Simone", "Isaiah",
    "Alicia", "Finn", "Kezia", "Tobias", "Miriam", "Elias", "Dani", "Kofi",
    "Ananya", "Felix", "Imani", "Hugo", "Selena", "Rowan", "Aziza", "Milo",
    "Chiara", "Eli", "Saoirse", "Declan", "Amina", "Sebastian", "Aria", "Kwame",
    "Talia", "Logan", "Zoe", "Reuben", "Nour", "Ezra", "Wren", "Matteo",
    "Iris", "Callum", "Eshe", "Bryce", "Lena", "Thiago", "Fiona", "Devlin",
    "Nasrin", "Cameron", "Blessing", "Kieran", "Mia", "Reid", "Seren", "Arlo",
    "Dalia", "Orion", "Juno", "Casimir", "Rue", "Soren", "Celeste", "Phineas",
    "Adaeze", "Stellan", "Nkechi", "Rafferty", "Indira", "Bastian", "Adeola", "Idris",
]

LAST_NAMES = [
    "Okonkwo", "Hernandez", "Nakamura", "Petrov", "Al-Hassan", "Mensah", "Johansson",
    "Okafor", "Fitzgerald", "Krishnan", "Balogun", "Larsson", "Mbeki", "Ramirez",
    "Tanaka", "Molina", "Andersen", "Diallo", "Yamamoto", "Ferreira", "Novak",
    "Oluwaseun", "MacLeod", "Svensson", "Nwosu", "Kowalski", "Abdi", "Bergström",
    "Oyewole", "Szymanski", "Adeyemi", "Lindqvist", "Achebe", "Reyes", "Watanabe",
    "Delacroix", "Eze", "Haugen", "Otieno", "Virtanen", "Afolabi", "Magnusson",
    "Opoku", "Castellanos", "Inoue", "Patel", "Eriksson", "Asante", "Nakagawa",
    "Nguyen", "Olawale", "Brandt", "Adichie", "Sorensen", "Dlamini", "Martins",
    "Nakamori", "Vásquez", "Olofsson", "Nkrumah", "Yamada", "Alvarado", "Thorsen",
    "Osei", "Cardenas", "Hayashi", "Moreau", "Bankole", "Lindberg", "Achola",
    "Fuentes", "Isaksson", "Ekwueme", "Salas", "Kobayashi", "Villanueva", "Halvorsen",
    "Owusu", "Quintero", "Suzuki", "Beaumont", "Ogundele", "Persson", "Acheson",
    "Vargas", "Fujimoto", "Lacroix", "Adebayo", "Holm", "Obinna", "Torres",
    "Nishimura", "Guerrero", "Bjornstad", "Fadahunsi", "Ibarra", "Matsumoto", "Mora",
]

# Fictional school IDs — format mimics real district/school coding conventions
SCHOOL_IDS = [
    "DIST001-SCH042", "DIST001-SCH071", "DIST001-SCH119",
    "DIST002-SCH003", "DIST002-SCH088", "DIST002-SCH215",
    "DIST003-SCH011", "DIST003-SCH034", "DIST003-SCH156",
    "DIST004-SCH007", "DIST004-SCH062", "DIST004-SCH088",
    "DIST005-SCH019", "DIST005-SCH041", "DIST005-SCH203",
    "DIST006-SCH055", "DIST006-SCH112", "DIST006-SCH178",
    "DIST007-SCH028", "DIST007-SCH091", "DIST007-SCH144",
    "DIST008-SCH016", "DIST008-SCH073", "DIST008-SCH201",
    "DIST009-SCH038", "DIST009-SCH095", "DIST009-SCH167",
    "DIST010-SCH004", "DIST010-SCH049", "DIST010-SCH188",
]

CREDENTIAL_TYPES = [
    "HIGH_SCHOOL_DIPLOMA",
    "GED",
    "CERTIFICATE_OF_COMPLETION",
    "HONORS_DIPLOMA",
    "ADVANCED_DIPLOMA",
    "VOCATIONAL_CERTIFICATE",
    "AP_CREDIT",
    "DUAL_ENROLLMENT",
    "SPECIAL_EDUCATION_DIPLOMA",
    "ALTERNATIVE_DIPLOMA",
]

# Status values per schema version are defined in generate_source_data.py
# These are the canonical status values used for reference
STATUS_VALUES = {
    "canonical": ["ACTIVE", "EXPIRED", "REVOKED", "PENDING"],
    "v1": ["ACTIVE", "EXPIRED", "REVOKED", "PENDING"],
    "v2": ["Active", "Expired", "Revoked", "Pending"],
    "v3": ["ACT", "EXP", "REV", "PND"],
    "v4": ["A", "E", "R", "P"],
    "v5": ["ACTIVE", "EXPIRED", "REVOKED", "PENDING"],
    "v6": ["active", "expired", "revoked", "pending"],
    "v7": ["Active", "Expired", "Revoked", "Pending"],
    "v8": ["ISSUED", "EXPIRED", "REVOKED", "DRAFT"],
}
