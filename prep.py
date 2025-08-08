# prep.py
from pathlib import Path
import csv, re, random, string
from datetime import datetime, timezone

random.seed(42)

FAIL_DIR = Path("data/logs/tf_fail")
PASS_DIR = Path("data/logs/tf_pass")
OUT_CSV  = Path("data/preparing.csv")
OUT_CSV.parent.mkdir(parents=True, exist_ok=True)

# Heavily favor PASS so the model sees lots of "good NIC with subnet_id"
AUG_PER_ROW_FAIL = 12
AUG_PER_ROW_PASS = 48

REGIONS = ["eastus", "eastus2", "japaneast", "westeurope", "uksouth"]
NAME_PAT = r'name\s*=\s*"([a-zA-Z0-9_\-]+)"'
ADDR_PAT = r'\["\d+\.\d+\.\d+\.0/\d+"\]'

def rand_suffix(k=3):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=k))

def _find(pat: str, text: str):
    m = re.search(pat, text)
    return m.group(1) if m else None

# ---------------- Reverse-engineer TF from a log (no token injection) ----------------
def infer_tf_from_log(raw: str, label: int) -> str:
    t = raw.lower()

    # Subnet missing
    if "subnetnotfound" in t or ("cannot find subnet" in t and "virtual network" in t):
        sub = _find(r"subnet named '([^']+)'", t) or _find(r"subnet '([^']+)'", t) or "subnet-prod"
        vnet = _find(r"virtual network '([^']+)'", t) or "vnet-main"
        return f'''resource "azurerm_virtual_network" "vnet" {{
  name                = "{vnet}"
  address_space       = ["10.0.0.0/16"]
  location            = "eastus"
  resource_group_name = "rg-prod-eastus"
}}

resource "azurerm_subnet" "subnet" {{
  name                 = "{sub}"
  resource_group_name  = "rg-prod-eastus"
  virtual_network_name = azurerm_virtual_network.vnet.name
  address_prefixes     = ["10.0.1.0/24"]
}}

resource "azurerm_network_interface" "nic" {{
  name                = "vmnic01"
  location            = "eastus"
  resource_group_name = "rg-prod-eastus"

  ip_configuration {{
    name                          = "internal"
    private_ip_address_allocation = "Dynamic"
    # intentionally no subnet reference here
  }}
}}'''

    # Route table missing/association invalid
    if ("route table" in t and ("resourcenotfound" in t or "not found" in t or "association invalid" in t)):
        subnet = _find(r"subnet '([^']+)'", t) or "web-subnet"
        rt     = _find(r'route table "([^"]+)"', t) or "rt-app"
        return f'''resource "azurerm_subnet" "web" {{
  name                 = "{subnet}"
  resource_group_name  = "rg-app-eastus"
  virtual_network_name = "vnet-app"
  address_prefixes     = ["10.0.2.0/24"]
}}

# Association references a route table that is not defined
resource "azurerm_subnet_route_table_association" "assoc" {{
  subnet_id      = azurerm_subnet.web.id
  route_table_id = azurerm_route_table.{rt}.id
}}'''

    # Authorization failed
    if "authorizationfailed" in t:
        return '''provider "azurerm" {
  features {}
  # likely missing/invalid credentials or wrong scope
}

data "azurerm_virtual_network" "target" {
  name                = "vnet-sec"
  resource_group_name = "rg-sec"
}'''

    # Quota exceeded
    if "quotaexceeded" in t:
        return '''resource "azurerm_resource_group" "rg" {
  name     = "rg-compute-eastus2"
  location = "eastus2"
}

resource "azurerm_subnet" "subnet" {
  name                 = "subnet-compute"
  resource_group_name  = azurerm_resource_group.rg.name
  virtual_network_name = "vnet-main"
  address_prefixes     = ["10.0.1.0/24"]
}

resource "azurerm_network_interface" "nic" {
  name                = "vmnic01"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name

  ip_configuration {
    name                          = "internal"
    subnet_id                     = azurerm_subnet.subnet.id
    private_ip_address_allocation = "Dynamic"
  }
}

resource "azurerm_linux_virtual_machine" "vm" {
  name                  = "vm-compute-01"
  resource_group_name   = azurerm_resource_group.rg.name
  location              = azurerm_resource_group.rg.location
  size                  = "Standard_D16s_v5"
  admin_username        = "azureuser"
  network_interface_ids = [azurerm_network_interface.nic.id]
}'''

    # Invalid storage account name
    if "invalidresourcename" in t or ("storage account name" in t and "lower-case" in t):
        bad = _find(r'storage account "([^"]+)"', t) or "Prod_Stor!"
        return f'''resource "azurerm_storage_account" "sa" {{
  name                     = "{bad}"
  resource_group_name      = "rg-storage"
  location                 = "eastus"
  account_tier             = "Standard"
  account_replication_type = "LRS"
}}'''

    # PASS logs → valid minimal network
    if label == 1:
        return '''resource "azurerm_resource_group" "rg" {
  name     = "rg-demo"
  location = "eastus"
}

resource "azurerm_virtual_network" "vnet" {
  name                = "vnet-main"
  address_space       = ["10.1.0.0/16"]
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
}

resource "azurerm_subnet" "subnet" {
  name                 = "subnet-app"
  resource_group_name  = azurerm_resource_group.rg.name
  virtual_network_name = azurerm_virtual_network.vnet.name
  address_prefixes     = ["10.1.1.0/24"]
}'''

    # Fallback
    return '''resource "azurerm_resource_group" "rg" {
  name     = "rg-unknown"
  location = "eastus"
}'''

# ---------------- PASS seeds (include your exact "perfect" pattern) ----------------
def make_pass_seeds() -> list[str]:
    base_net = '''resource "azurerm_resource_group" "rg" {
  name     = "rg-demo"
  location = "eastus"
}

resource "azurerm_virtual_network" "vnet" {
  name                = "vnet-main"
  address_space       = ["10.1.0.0/16"]
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
}

resource "azurerm_subnet" "subnet" {
  name                 = "subnet-app"
  resource_group_name  = azurerm_resource_group.rg.name
  virtual_network_name = azurerm_virtual_network.vnet.name
  address_prefixes     = ["10.1.1.0/24"]
}'''
    # Valid NIC wired to defined subnet (typical good case)
    nic_ok = base_net + '''
resource "azurerm_network_interface" "nic" {
  name                = "vmnic-ok"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name

  ip_configuration {
    name                          = "internal"
    subnet_id                     = azurerm_subnet.subnet.id
    private_ip_address_allocation = "Dynamic"
  }
}'''
    # Valid RT association
    rt_ok = base_net + '''
resource "azurerm_route_table" "rt" {
  name                = "rt-ok"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
}

resource "azurerm_subnet_route_table_association" "assoc" {
  subnet_id      = azurerm_subnet.subnet.id
  route_table_id = azurerm_route_table.rt.id
}'''
    # Valid storage account
    sa_ok = '''
resource "azurerm_resource_group" "rg" {
  name     = "rg-storage-ok"
  location = "eastus"
}

resource "azurerm_storage_account" "sa" {
  name                     = "storaaaaaaaa01"
  resource_group_name      = azurerm_resource_group.rg.name
  location                 = azurerm_resource_group.rg.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
}'''
    # *** Your exact "perfect" pattern: NIC + subnet, NO vnet resource ***
    nic_ok_no_vnet = '''
resource "azurerm_network_interface" "nic" {
  name                = "vmnic01"
  location            = "eastus"
  resource_group_name = "rg-prod-eastus"

  ip_configuration {
    name                          = "internal"
    subnet_id                     = azurerm_subnet.subnet-prod.id
    private_ip_address_allocation = "Dynamic"
  }
}

resource "azurerm_subnet" "subnet-prod" {
  name                 = "subnet-prod"
  resource_group_name  = "rg-prod-eastus"
  virtual_network_name = "vnet-main"
  address_prefixes     = ["10.0.1.0/24"]
}'''
    # Weight your pattern heavier
    return [base_net, nic_ok, rt_ok, sa_ok] + [nic_ok_no_vnet] * 6

# ---------------- Augmentation (text-only) ----------------
def vary_names(tf: str) -> str:
    def repl(m):
        base = m.group(1)
        return f'name = "{base}-{rand_suffix(2)}"'
    return re.sub(NAME_PAT, repl, tf)

def vary_region(tf: str) -> str:
    return re.sub(r'location\s*=\s*"[^"]+"', lambda _: f'location = "{random.choice(REGIONS)}"', tf)

def vary_prefix(tf: str) -> str:
    return re.sub(ADDR_PAT, lambda _: f'["10.{random.randint(0,9)}.{random.randint(0,9)}.0/24"]', tf)

def add_comments(tf: str) -> str:
    if random.random() < 0.5:
        tf = f'# generated {datetime.now(timezone.utc).isoformat()}\n' + tf
    if random.random() < 0.5:
        tf = tf + "\n# eof\n"
    return tf

def augment(tf: str) -> str:
    x = tf
    x = vary_region(vary_names(vary_prefix(x)))
    return add_comments(x)

def augment_fail(tf: str, k: int) -> list[str]:
    out = []
    for _ in range(k):
        x = augment(tf)
        # ensure any accidental subnet_id occurrences are removed for FAIL
        x = re.sub(r'\s*subnet_id\s*=\s*[^\n}]+', '', x)
        x = re.sub(r'.*subnet_id.*\n', '', x, flags=re.IGNORECASE)
        out.append(x)
    return out

def augment_pass(tf: str, k: int) -> list[str]:
    seeds = make_pass_seeds() + [tf]  # include base from pass log too
    out = []
    for _ in range(k):
        x = augment(random.choice(seeds))
        out.append(x)
    return out

# ---------------- Collect & write ----------------
def collect_rows() -> list[dict]:
    rows = []
    if FAIL_DIR.exists():
        for p in sorted(FAIL_DIR.glob("*.log")):
            raw = p.read_text(encoding="utf-8")
            base = infer_tf_from_log(raw, 0)
            for j, v in enumerate(augment_fail(base, AUG_PER_ROW_FAIL)):
                rows.append({"id": f"{p.name}::f{j:02d}", "group_id": p.name, "label": 0, "tf_snippet": v})
    if PASS_DIR.exists():
        for p in sorted(PASS_DIR.glob("*.log")):
            raw = p.read_text(encoding="utf-8")
            base = infer_tf_from_log(raw, 1)
            for j, v in enumerate(augment_pass(base, AUG_PER_ROW_PASS)):
                rows.append({"id": f"{p.name}::p{j:02d}", "group_id": p.name, "label": 1, "tf_snippet": v})
    return rows

if __name__ == "__main__":
    rows = collect_rows()
    if not rows:
        raise SystemExit("No logs found. Put .log files in data/logs/tf_fail and/or data/logs/tf_pass.")

    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["id","group_id","label","tf_snippet"])
        w.writeheader(); w.writerows(rows)

    c0 = sum(1 for r in rows if r["label"] == 0)
    c1 = len(rows) - c0
    print(f"Wrote {len(rows)} rows → {OUT_CSV}")
    print(f"Class balance: fail=0 → {c0} | pass=1 → {c1}")
