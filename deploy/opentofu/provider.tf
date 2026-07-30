terraform {
  required_version = ">= 1.0.0"
  required_providers {
    openstack = {
      source  = "terraform-provider-openstack/openstack"
      version = "~> 2.1"
    }
    cloudinit = {
      source  = "hashicorp/cloudinit"
      version = "~> 2.3.0"
    }
  }
}

# Reads the "openstack" entry from ~/.config/openstack/clouds.yaml
# (export OS_CLOUD=openstack, or rely on the default clouds.yaml lookup path).
provider "openstack" {
  cloud = "openstack"
}
