"""Backend entry points: API and CLI. Depends on core/, governance/, and
ai/ only.

``interfaces/dashboard/`` (the Next.js frontend) is not part of this Python
package — it is a separate Node.js application that talks to
``interfaces/api/app.py`` over HTTP and is never imported from here.
"""
