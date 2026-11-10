/**
 * Centralized Internationalization (i18n) Dictionary
 * English default, structured for simple addition of Tamil / Hindi / other languages.
 */

const translations = {
  en: {
    appTitle: "Farmer Slot Booking System",
    portalSubtitle: "Session-wise Produce Selling Slots",
    
    // Status Chips
    available: "Available",
    almostFull: "Almost full",
    full: "Full",
    closed: "Closed",
    booked: "Booked",
    checkedIn: "Checked In",
    called: "Called to Desk",
    completed: "Completed & Paid",
    missed: "Missed",
    noShow: "No-Show",
    cancelled: "Cancelled",

    // Common Buttons
    bookSlot: "Book Slot",
    confirmBooking: "Confirm Booking",
    cancelBooking: "Cancel Booking",
    printReceipt: "Print Receipt",
    bookNewSlot: "Book a New Slot",
    login: "Log In",
    logout: "Log Out",
    register: "Register Profile",
    callNext: "Call Next Customer",
    completePaid: "Paid in Cash - Complete",
    markNoShow: "Mark No-Show",
    scanQR: "Scan QR",
    saveChanges: "Save Changes",

    // Messages
    bookingConfirmed: "Your produce selling slot has been reserved successfully.",
    bookingCancelConfirm: "Are you sure you want to cancel this booking? The seat will be released immediately.",
    bookingCancelledSuccess: "Booking cancelled successfully.",
    invalidQR: "Invalid or unrecognized QR token.",
    gateSuccess: "Check-in Successful! Assigned Queue position:",
    officeServeSuccess: "Produce verified and payment completed successfully.",
    estimateDisclaimer: "Estimate only — final amount is based on actual produce weight verified at the counter."
  }
};

let currentLocale = "en";

export function t(key) {
  return translations[currentLocale]?.[key] || key;
}

export function setLocale(locale) {
  if (translations[locale]) {
    currentLocale = locale;
  }
}

