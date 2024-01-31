export default {
  formatTimestamp(timestamp) {
    // Extract year, month, day, hours, minutes, and seconds from the string
    const timestampStr = String(timestamp);
    const year = timestampStr.substring(0, 4);
    const month = timestampStr.substring(4, 6) - 1; // Month is 0-indexed in JavaScript Date
    const day = timestampStr.substring(6, 8);

    // Create a new Date object
    const date = new Date(year, month, day);

    // Format the date to dd-MM-yyyy
    return date.toLocaleDateString('en-GB', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    });
  },

  formatISO8601Date(timestamp) {
    const timestampStr = String(timestamp);

    const year = timestamp.substring(0, 4);
    const month = timestamp.substring(4, 6) - 1; // Month is 0-indexed in JavaScript Date
    const day = timestamp.substring(6, 8);
    const hour = timestamp.substring(8, 10);
    const minute = timestamp.substring(10, 12);
    const second = timestamp.substring(12, 14);

    // Create a new Date object
    const date = new Date(Date.UTC(year, month, day, hour, minute, second));

    // Format the date to ISO 8601
    return date.toISOString();
  },

  getCsrfToken() {
    return document.querySelector('[name=csrfmiddlewaretoken]').value;
  },
};
