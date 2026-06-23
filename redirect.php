<?php
// --- Smart PHP Redirect & Click Logger for Advanced Sender ultra ---

// 1. CONFIGURATION
// ------------------------------------------------------------------
// The file where clicks will be logged. Ensure this file is writable by the web server.
$logFile = 'clicks.log';

// The secret key for verifying link signatures. This MUST match the 'tracking_secret_key' in your config.ini.
$secretKey = 'IDUh7hbn8xb8h9js8m9UjIIODOusjeum!';

// The default URL to redirect to if the destination is missing or invalid.
$fallbackUrl = 'https://track.circlesrenergy.com';

// Set the timezone for consistent timestamps.
// A list of supported timezones can be found here: https://www.php.net/manual/en/timezones.php
date_default_timezone_set('UTC');

// 2. CAPTURE CLICK DATA
// ------------------------------------------------------------------
// Get the base64 encoded destination URL and the unique user ID from the query string.
// e.g., redirect.php?dest=aHR0cHM6Ly9leGFtcGxlLmNvbQ==&uid=aW5mb0BleGFtcGxlLmNvbQ==
$encodedDestination = isset($_GET['dest']) ? $_GET['dest'] : null;
$uniqueId = isset($_GET['uid']) ? $_GET['uid'] : 'unknown';
$signature = isset($_GET['sig']) ? $_GET['sig'] : null;

// Get visitor information.
$timestamp = date('Y-m-d H:i:s');
$ipAddress = $_SERVER['REMOTE_ADDR'];
$userAgent = $_SERVER['HTTP_USER_AGENT'];

// 3. DECODE, VALIDATE, AND LOG
// ------------------------------------------------------------------
// --- "Smarter" HMAC Signature Verification ---
// Recreate the signature on the server side.
$message = $encodedDestination . $uniqueId;
$expectedSignature = hash_hmac('sha256', $message, $secretKey);

// Decode the destination URL from base64.
$destinationUrl = $encodedDestination ? base64_decode($encodedDestination) : null;

// Only proceed if the signature is valid AND the destination is a valid URL.
// hash_equals is used for a timing-attack-safe comparison.
if ($signature && hash_equals($expectedSignature, $signature) && $destinationUrl && filter_var($destinationUrl, FILTER_VALIDATE_URL)) {
    // Format the log entry. Using tabs (\t) is good practice.
    $logEntry = $timestamp . "\t" . $ipAddress . "\t" . $uniqueId . "\t" . $userAgent . "\t" . $destinationUrl . "\n";

    // Append the log entry to the log file.
    file_put_contents($logFile, $logEntry, FILE_APPEND | LOCK_EX);

    // --- "Smart" Micro-Delay ---
    // A small, random delay can make automated analysis of the redirect slightly more difficult.
    usleep(random_int(50000, 150000)); // Sleep for 50-150 milliseconds

    // 4. REDIRECT
    // ------------------------------------------------------------------
    // Perform a 302 redirect to the final destination.
    header("Location: " . $destinationUrl);
    exit;

} else {
    // 5. HANDLE ERRORS (Invalid Signature or Malformed URL)
    // ------------------------------------------------------------------
    // If the signature is invalid, log it as a tampered request.
    $errorReason = "INVALID_SIGNATURE";
    if (!$destinationUrl || !filter_var($destinationUrl, FILTER_VALIDATE_URL)) {
        $errorReason = "INVALID_DEST_URL";
    }
    $logEntry = $timestamp . "\t" . $ipAddress . "\t" . $uniqueId . "\t" . $userAgent . "\t" . $errorReason . "\n";
    file_put_contents($logFile, $logEntry, FILE_APPEND | LOCK_EX);
    header("Location: " . $fallbackUrl);
    exit;
}
?>