<?php
// --- Simple PHP Redirect & Click Logger ---

// 1. CONFIGURATION
// ------------------------------------------------------------------
// The file where clicks will be logged. Ensure this file is writable by the web server.
$logFile = 'clicks.log';

// Set the timezone for consistent timestamps.
// A list of supported timezones can be found here: https://www.php.net/manual/en/timezones.php
date_default_timezone_set('UTC');

// 2. CAPTURE CLICK DATA
// ------------------------------------------------------------------
// Get the destination URL from the query string. e.g., redirect.php?url=https://example.com
$destinationUrl = isset($_GET['url']) ? $_GET['url'] : null;

// Get visitor information.
$timestamp = date('Y-m-d H:i:s');
$ipAddress = $_SERVER['REMOTE_ADDR'];
$userAgent = $_SERVER['HTTP_USER_AGENT'];

// 3. VALIDATE AND LOG
// ------------------------------------------------------------------
// Only proceed if the destination URL is a valid URL format.
if (filter_var($destinationUrl, FILTER_VALIDATE_URL)) {
    // Format the log entry as a CSV (Comma Separated Value) line.
    // Using tabs (\t) as a separator makes it easier to read if URLs contain commas.
    $logEntry = $timestamp . "\t" . $ipAddress . "\t" . $userAgent . "\t" . $destinationUrl . "\n";

    // Append the log entry to the log file.
    // The FILE_APPEND flag ensures we don't overwrite the file each time.
    // The LOCK_EX flag prevents other processes from writing to the file at the same time.
    file_put_contents($logFile, $logEntry, FILE_APPEND | LOCK_EX);

    // 4. REDIRECT
    // ------------------------------------------------------------------
    // Perform a 302 redirect to the final destination.
    header("Location: " . $destinationUrl);
    exit; // Ensure no further code is executed after the redirect.

} else {
    // 5. HANDLE ERRORS
    // ------------------------------------------------------------------
    // If the URL is missing or invalid, display an error message.
    // In a production environment, you might want to redirect to a generic homepage.
    header("HTTP/1.0 400 Bad Request");
    echo "Error: Invalid or missing destination URL.";
    
    // Optionally, log the bad request attempt.
    $logEntry = $timestamp . "\t" . $ipAddress . "\t" . $userAgent . "\t" . "INVALID_URL_REQUEST" . "\n";
    file_put_contents($logFile, $logEntry, FILE_APPEND | LOCK_EX);
    exit;
}
?>