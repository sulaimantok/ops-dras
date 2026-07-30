# --- Data Sources ---
data "openstack_networking_network_v2" "internal_net" {
  name = var.network_name
}

data "openstack_images_image_v2" "os_image" {
  name        = var.image_name
  most_recent = true
}

# Resolve the existing lab-wide security groups (e.g. sg-learn) by name to id,
# since attaching an explicit port bypasses the instance-level security_groups
# argument and requires security_group_ids on the port instead.
data "openstack_networking_secgroup_v2" "existing" {
  for_each = toset(var.security_groups)
  name     = each.value
}

# --- Dedicated Security Group for testing the ops-dras web UI ---
resource "openstack_networking_secgroup_v2" "app_test" {
  name        = "sg-ops-dras-test"
  description = "SSH + ops-dras UI access for the ops-dras test VM"
}

resource "openstack_networking_secgroup_rule_v2" "ssh" {
  for_each          = toset(var.allowed_ssh_cidr)
  direction         = "ingress"
  ethertype         = "IPv4"
  protocol          = "tcp"
  port_range_min    = 22
  port_range_max    = 22
  remote_ip_prefix  = each.value
  security_group_id = openstack_networking_secgroup_v2.app_test.id
}

resource "openstack_networking_secgroup_rule_v2" "app_ui" {
  for_each          = toset(var.allowed_app_cidr)
  direction         = "ingress"
  ethertype         = "IPv4"
  protocol          = "tcp"
  port_range_min    = var.app_port
  port_range_max    = var.app_port
  remote_ip_prefix  = each.value
  security_group_id = openstack_networking_secgroup_v2.app_test.id
}

# --- Networking Port (static IP on internal0) ---
resource "openstack_networking_port_v2" "ops_dras_port" {
  name           = "${var.instance_name}-port"
  network_id     = data.openstack_networking_network_v2.internal_net.id
  admin_state_up = "true"

  security_group_ids = concat(
    [for sg in data.openstack_networking_secgroup_v2.existing : sg.id],
    [openstack_networking_secgroup_v2.app_test.id],
  )

  fixed_ip {
    subnet_id  = var.subnet_id
    ip_address = var.instance_ip
  }
}

# --- Cloud Init: provisions Docker + Docker Compose plugin for testing ---
data "cloudinit_config" "user_data" {
  gzip          = false
  base64_encode = false

  part {
    content_type = "text/cloud-config"
    content      = file("${path.module}/cloud_init.yaml")
  }
}

# --- Compute Instance ---
resource "openstack_compute_instance_v2" "ops_dras_test" {
  name        = var.instance_name
  flavor_name = var.flavor_name
  key_pair    = var.keypair_name

  block_device {
    uuid                  = data.openstack_images_image_v2.os_image.id
    source_type           = "image"
    volume_size           = var.boot_volume_size
    boot_index            = 0
    destination_type      = "volume"
    delete_on_termination = true
  }

  user_data = data.cloudinit_config.user_data.rendered

  network {
    port = openstack_networking_port_v2.ops_dras_port.id
  }
}

# --- Floating IP so the app UI is reachable from outside the lab network ---
resource "openstack_networking_floatingip_v2" "ops_dras_fip" {
  pool = var.public_network_name
}

resource "openstack_networking_floatingip_associate_v2" "ops_dras_fip_assoc" {
  floating_ip = openstack_networking_floatingip_v2.ops_dras_fip.address
  port_id     = openstack_networking_port_v2.ops_dras_port.id
}
