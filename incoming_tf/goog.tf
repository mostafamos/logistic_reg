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
}
