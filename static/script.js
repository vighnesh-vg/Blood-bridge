
function updateInventory(bloodType, action) {
    const quantity = document.getElementById(`update-${bloodType}`).value;
    if (!quantity) {
        alert("Please enter a quantity!");
        return;
    }
    fetch('/update-inventory', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ blood_type: bloodType, quantity: parseInt(quantity), action }),
    })
        .then(response => response.json())
        .then(data => {
            alert(data.message);
            location.reload();
        })
        .catch(error => console.error('Error:', error));
}
