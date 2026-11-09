# nix/devShell.nix — Dev shell that delegates setup to each package
#
# Each npm workspace package exposes passthru.packageJsonPath (e.g.
# "ui-tui/package.json").  This file collects them all and passes the
# list to mkNpmDevShellHook, which stamps all package.jsons at once,
# then runs a single `npm i --package-lock-only` if any changed and
# `npm ci` if the lockfile changed.
{ ... }:
{
  perSystem =
    { pkgs, lib, self', ... }:
    let
      packages = builtins.attrValues self'.packages;
      zeusNpmLib = self'.packages.default.passthru.zeusNpmLib;

      # Collect all packageJsonPath values from npm workspace packages.
      npmPackageJsonPaths = builtins.filter (p: p != null) (
        map (p: p.passthru.packageJsonPath or null) packages
      );

      zeusAgentsDevShellHook = self'.packages.default.passthru.devShellHook;
    in
    {
      devShells.default = pkgs.mkShell {
        packages = with pkgs; [
          (pkgs.runCommand "zeus" { } ''
            mkdir -p $out/bin
            install -Dm755 ${../zeus} $out/bin/zeus
          '')
          self'.packages.sandbox
        ]
        # Wayland-only: cage and ghostty pull alsa-lib, which does not
        # evaluate on darwin.
        ++ lib.optionals pkgs.stdenv.hostPlatform.isLinux [
          # Headless Wayland compositor: cage renders a single client with
          # no window management. libglvnd provides libEGL.so.1 that cage
          # needs on NixOS.
          cage
          libglvnd
          # Graphical terminal + Wayland screenshot client for CLI/TUI UI
          # evidence. `cage -- ghostty ...` keeps captures off the user's
          # live compositor; grim runs inside that isolated client session.
          ghostty
          grim
        ]
        ++ self'.packages.default.passthru.devDeps;
        shellHook = ''
          # The editable venv's .pth resolves the checkout through this.
          export ZEUS_PYTHON_SRC_ROOT=$(git rev-parse --show-toplevel)

          ${zeusAgentsDevShellHook}
          ${zeusNpmLib.mkNpmDevShellHook npmPackageJsonPaths}

          # Force Node to use Nix's playwright-test binary instead of node_modules/.bin
          export PATH="${pkgs.playwright-test}/bin:$PATH"

          # The lock's interpreter is python-build-standalone, whose OpenSSL has
          # no compiled-in NixOS trust store; point it at the CA bundle so
          # urllib/httpx/requests verify certificates like the nixpkgs one.
          export SSL_CERT_FILE="${pkgs.cacert}/etc/ssl/certs/ca-bundle.crt"
          export NIX_SSL_CERT_FILE="$SSL_CERT_FILE"

          echo "Zeus Agents dev shell in $ZEUS_PYTHON_SRC_ROOT"
          echo "Ready. Run 'zeus' or 'sandbox zeus' to start."
        '';
      };
    };
}
