#pragma once

// Define this as a plain string literal in a_def_pass.h or build flags.
// Do not provide a shared/default password: missing configuration must fail closed.
#ifndef PANEL_ADMIN_PASSWORD
#error "Define PANEL_ADMIN_PASSWORD as a unique password (at least 16 characters) in a_def_pass.h or build flags."
#else
static_assert(sizeof(PANEL_ADMIN_PASSWORD) >= 17,
              "PANEL_ADMIN_PASSWORD must contain at least 16 characters.");
static const char PANEL_ADMIN_USER[] = "admin";
#endif
