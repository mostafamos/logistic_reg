resource "azurerm_network_interface" "nic" {
  name                = "vmnic01"
  location            = "eastus"
  resource_group_name = "rg-prod-eastus"

  ip_configuration {
    name                          = "internal"
    private_ip_address_allocation = "Dynamic"
    # subnet_id is missing here
  }
}
