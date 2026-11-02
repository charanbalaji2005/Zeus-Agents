# shellcheck shell=sh
# Installed as /etc/profile.d/zeus.sh. Debian's /etc/profile resets PATH for
# every login shell (`bash -l`, `docker exec <c> bash -l`, ssh, the terminal
# tool's background `bash -lic`), dropping the image's ENV PATH dirs, so bare
# `zeus` exits 127 there. Put them back in the ENV PATH order; dirs a login
# PATH already lists keep their position.
for __zeus_p in /opt/data/.local/bin /opt/zeus/.venv/bin /opt/zeus/bin; do
    case ":$PATH:" in
        *":$__zeus_p:"*) ;;
        *) PATH="$__zeus_p:$PATH" ;;
    esac
done
unset __zeus_p
export PATH
