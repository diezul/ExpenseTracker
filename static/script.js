document.addEventListener('DOMContentLoaded', () => {
    const monthInputs = document.querySelectorAll('input[type="month"]');
    const tooltips = document.querySelectorAll('.tooltip');
    const textInputs = document.querySelectorAll('input[type="text"]');
    const serviceInputs = document.querySelectorAll('#fixed_service_input, #variable_service_input');

    // Add focus event to month inputs to show the date picker
    monthInputs.forEach(input => {
        input.addEventListener('focus', () => {
            input.showPicker();
        });
    });

    // Enforce lowercase for text inputs
    textInputs.forEach(input => {
        input.addEventListener('input', () => {
            input.value = input.value.toLowerCase();
        });
    });

    // Add focus and input event to service inputs to show suggestions
    serviceInputs.forEach(input => {
        input.addEventListener('focus', () => {
            const type = input.id.replace('_service_input', '');
            showSuggestions(type, true);  // true to indicate focus event
        });

        input.addEventListener('input', () => {
            const type = input.id.replace('_service_input', '');
            showSuggestions(type, false);  // false to indicate input event
        });

        // Close suggestions box when input loses focus
        input.addEventListener('blur', () => {
            const suggestionsBox = document.getElementById(`${input.id.replace('_input', '')}_suggestions`);
            setTimeout(() => {
                suggestionsBox.innerHTML = ''; // Clear suggestions after losing focus
            }, 200); // Timeout to allow clicking on suggestions
        });
    });

    // Close all tooltips when clicking anywhere on the document
    document.addEventListener('click', () => {
        closeAllTooltips();
    });

    function closeAllTooltips() {
        tooltips.forEach(tooltip => {
            tooltip.classList.remove('active');
        });
    }
});

// Function to show suggestions for service input fields
function showSuggestions(type, isFocusEvent) {
    const input = document.getElementById(`${type}_service_input`);
    const suggestionsBox = document.getElementById(`${type}_service_suggestions`);
    const query = input.value.trim();

    suggestionsBox.style.width = `${input.offsetWidth}px`;
    suggestionsBox.style.display = 'block';  // Ensure suggestions box is visible

    fetch(`/search_service/${type}?q=` + query)
        .then(response => response.json())
        .then(data => {
            suggestionsBox.innerHTML = '';
            if (data.services.length > 0 || (query.length > 0 && !isFocusEvent)) {
                data.services.forEach(service => {
                    const suggestion = document.createElement('div');
                    suggestion.className = 'suggestion-item';
                    suggestion.innerHTML = `
                        ${service}
                        <button type="button" class="delete-service" onclick="confirmDeleteService('${type}', '${service}')">
                            <i class="fas fa-times" style="color: blue;"></i>
                        </button>
                    `;
                    suggestion.onclick = () => {
                        input.value = service;
                        suggestionsBox.innerHTML = '';
                    };
                    suggestionsBox.appendChild(suggestion);
                });

                if (query.length > 0 && !isFocusEvent) {
                    const addNewOption = document.createElement('div');
                    addNewOption.className = 'suggestion-item';
                    addNewOption.innerHTML = `Add ${query} to the list of your services`;
                    addNewOption.onclick = () => {
                        addServiceDirect(type, query);
                        input.value = query;
                        suggestionsBox.innerHTML = '';
                    };
                    suggestionsBox.appendChild(addNewOption);
                }
            }
        });
}

// Function to add a new service directly
function addServiceDirect(type, serviceName) {
    fetch(`/add_service_direct/${type}/${serviceName}`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
        }
    }).then(response => response.json())
      .then(data => {
        showNotification(data.message);
    });
}

// Function to show delete confirmation modal for services
function confirmDeleteService(type, serviceName) {
    $('#deleteServiceModal').modal('show');
    document.getElementById('confirmDeleteServiceButton').onclick = function () {
        deleteService(type, serviceName);
        $('#deleteServiceModal').modal('hide');
    };
}

// Function to delete a service
function deleteService(type, serviceName) {
    const input = document.getElementById(`${type}_service_input`);
    fetch(`/delete_service/${type}`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: new URLSearchParams({
            service_name: serviceName
        })
    }).then(response => {
        if (response.ok) {
            input.value = ''; // Clear the input box
            showNotification(`The service ${serviceName} was successfully deleted!`);
        } else {
            showNotification('An error occurred. Please try again.');
        }
    });
}

// Function to show delete confirmation modal for expenses
function confirmDelete(expenseId, serviceName) {
    $('#confirmDeleteButton').attr('onclick', `deleteExpense(${expenseId}, '${serviceName}')`);
    $('#confirmDeleteModal').modal('show');
}

// Function to delete an expense
function deleteExpense(expenseId, serviceName) {
    $('#confirmDeleteModal').modal('hide'); // Close the modal
    fetch(`/delete/${expenseId}`, {
        method: 'POST'
    }).then(response => {
        if (response.ok) {
            showNotification(`The bill for ${serviceName} was successfully deleted!`, true);
        } else {
            showNotification('An error occurred. Please try again.');
        }
    });
}

// Function to mark an expense as paid
function markAsPaid(expenseId, serviceName) {
    fetch(`/pay/${expenseId}`, {
        method: 'POST'
    }).then(response => {
        if (response.ok) {
            showNotification(`The service ${serviceName} has been marked as paid!`, true);
        } else {
            showNotification('An error occurred. Please try again.');
        }
    });
}

// Ensure the modal closes when cancel button or close (X) button is clicked
$(document).ready(function() {
    $('#confirmDeleteModal .btn-secondary, #confirmDeleteModal .close').click(function() {
        $('#confirmDeleteModal').modal('hide');
    });

    $('#deleteServiceModal .btn-secondary, #deleteServiceModal .close').click(function() {
        $('#deleteServiceModal').modal('hide');
    });
});

// Function to show notifications
function showNotification(message, reload = false) {
    const notification = document.getElementById('notification');
    notification.textContent = message;
    notification.classList.add('show');
    setTimeout(() => {
        notification.classList.remove('show');
        if (reload) {
            location.reload();
        }
    }, 3000);
}
