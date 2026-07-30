variable "instance_name" {
  description = "Nama VM lab untuk testing aplikasi ops-dras"
  default     = "ops-dras-test"
}

variable "image_name" {
  description = "Nama Image di OpenStack"
  default     = "Ubuntu 24.04 ARM64"
}

variable "flavor_name" {
  description = "Nama Flavor"
  default     = "m1.small"
}

variable "network_name" {
  description = "Nama Internal Network"
  default     = "internal0"
}

variable "subnet_id" {
  description = "ID dari Subnet internal0"
  default     = "1c043d79-8580-42f2-be5e-3e17d741527b"
}

variable "public_network_name" {
  description = "Nama Public/External Network untuk Floating IP"
  default     = "public"
}

variable "keypair_name" {
  description = "Nama SSH Keypair"
  default     = "sulaiman"
}

variable "security_groups" {
  description = "Security group standar lab (existing) yang ikut dipasang di VM ini"
  type        = list(string)
  default     = ["sg-learn"]
}

variable "instance_ip" {
  description = "Static internal IP untuk VM test (di luar range .10-.15 yang dipakai lab RHCE)"
  default     = "192.168.10.20"
}

variable "boot_volume_size" {
  description = "Ukuran disk boot (GB) untuk Docker images, PostgreSQL, log, dan backup database"
  default     = 20
}

variable "app_port" {
  description = "Port HTTP aplikasi ops-dras (gunicorn di container)"
  default     = 8080
}

variable "allowed_app_cidr" {
  description = "CIDR yang diizinkan mengakses UI ops-dras di app_port. Persempit jika lab dipakai bersama."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "allowed_ssh_cidr" {
  description = "CIDR yang diizinkan SSH ke VM test"
  type        = list(string)
  default     = ["0.0.0.0/0"]
}
