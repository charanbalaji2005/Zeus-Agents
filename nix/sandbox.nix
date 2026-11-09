# The dev sandbox runs a command against an isolated ZEUS_HOME; nothing in
# it is nix-specific, so the package only puts the script on PATH.
{
  writeShellApplication,
}:
writeShellApplication {
  name = "sandbox";
  text = ''
    exec ${../scripts/dev-sandbox.sh} "$@"
  '';
}
