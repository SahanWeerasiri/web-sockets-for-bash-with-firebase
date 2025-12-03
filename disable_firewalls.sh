# Completely disable all firewalls
sudo systemctl stop firewalld 2>/dev/null
sudo systemctl disable firewalld 2>/dev/null
sudo systemctl stop ufw
sudo systemctl disable ufw
sudo iptables -F
sudo iptables -X
sudo iptables -t nat -F
sudo iptables -t nat -X
sudo iptables -t mangle -F
sudo iptables -t mangle -X
sudo iptables -P INPUT ACCEPT
sudo iptables -P FORWARD ACCEPT
sudo iptables -P OUTPUT ACCEPT
sudo netfilter-persistent save 2>/dev/null || true
sudo systemctl restart firebase-rtdb