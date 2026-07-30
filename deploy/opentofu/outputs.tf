output "floating_ip" {
  description = "Public/Floating IP untuk SSH dan akses UI ops-dras"
  value       = openstack_networking_floatingip_v2.ops_dras_fip.address
}

output "internal_ip" {
  description = "Internal IP VM di network internal0"
  value       = var.instance_ip
}

output "ssh_command" {
  description = "Perintah SSH ke VM test"
  value       = "ssh ubuntu@${openstack_networking_floatingip_v2.ops_dras_fip.address}"
}

output "app_url" {
  description = "URL untuk membuka UI ops-dras setelah aplikasi di-deploy dan container jalan"
  value       = "http://${openstack_networking_floatingip_v2.ops_dras_fip.address}:${var.app_port}"
}
