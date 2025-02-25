import asyncio
import functools
import os
import pathlib
import shutil
import sys
import tempfile
from typing import Optional
from unittest import mock
from unittest.mock import MagicMock

import pytest
import yarl

from aiohttp import abc, web
from aiohttp.pytest_plugin import AiohttpClient
from aiohttp.web_urldispatcher import SystemRoute


@pytest.fixture(scope="function")
def tmp_dir_path(request):
    """
    Give a path for a temporary directory

    The directory is destroyed at the end of the test.
    """
    # Temporary directory.
    tmp_dir = tempfile.mkdtemp()

    def teardown():
        # Delete the whole directory:
        shutil.rmtree(tmp_dir)

    request.addfinalizer(teardown)
    return tmp_dir


@pytest.mark.parametrize(
    "show_index,status,prefix,request_path,data",
    [
        pytest.param(False, 403, "/", "/", None, id="index_forbidden"),
        pytest.param(
            True,
            200,
            "/",
            "/",
            b"<html>\n<head>\n<title>Index of /.</title>\n"
            b"</head>\n<body>\n<h1>Index of /.</h1>\n<ul>\n"
            b'<li><a href="/my_dir">my_dir/</a></li>\n'
            b'<li><a href="/my_file">my_file</a></li>\n'
            b"</ul>\n</body>\n</html>",
            id="index_root",
        ),
        pytest.param(
            True,
            200,
            "/static",
            "/static",
            b"<html>\n<head>\n<title>Index of /.</title>\n"
            b"</head>\n<body>\n<h1>Index of /.</h1>\n<ul>\n"
            b'<li><a href="/static/my_dir">my_dir/</a></li>\n'
            b'<li><a href="/static/my_file">my_file</a></li>\n'
            b"</ul>\n</body>\n</html>",
            id="index_static",
        ),
        pytest.param(
            True,
            200,
            "/static",
            "/static/my_dir",
            b"<html>\n<head>\n<title>Index of /my_dir</title>\n</head>\n<body>\n<h1>"
            b'Index of /my_dir</h1>\n<ul>\n<li><a href="/static/my_dir/my_file_in_dir">'
            b"my_file_in_dir</a></li>\n</ul>\n</body>\n</html>",
            id="index_subdir",
        ),
    ],
)
async def test_access_root_of_static_handler(
    tmp_dir_path: pathlib.Path,
    aiohttp_client: AiohttpClient,
    show_index: bool,
    status: int,
    prefix: str,
    request_path: str,
    data: Optional[bytes],
) -> None:
    # Tests the operation of static file server.
    # Try to access the root of static file server, and make
    # sure that correct HTTP statuses are returned depending if we directory
    # index should be shown or not.
    # Put a file inside tmp_dir_path:
    my_file_path = os.path.join(tmp_dir_path, "my_file")
    with open(my_file_path, "w") as fw:
        fw.write("hello")

    my_dir_path = os.path.join(tmp_dir_path, "my_dir")
    os.mkdir(my_dir_path)

    my_file_path = os.path.join(my_dir_path, "my_file_in_dir")
    with open(my_file_path, "w") as fw:
        fw.write("world")

    app = web.Application()

    # Register global static route:
    app.router.add_static(prefix, tmp_dir_path, show_index=show_index)
    client = await aiohttp_client(app)

    # Request the root of the static directory.
    r = await client.get(request_path)
    assert r.status == status

    if data:
        assert r.headers["Content-Type"] == "text/html; charset=utf-8"
        read_ = await r.read()
        assert read_ == data


@pytest.mark.skipif(
    not sys.platform.startswith("linux"),
    reason="Invalid filenames on some filesystems (like Windows)",
)
@pytest.mark.parametrize(
    "show_index,status,prefix,request_path,data",
    [
        pytest.param(False, 403, "/", "/", None, id="index_forbidden"),
        pytest.param(
            True,
            200,
            "/",
            "/",
            b"<html>\n<head>\n<title>Index of /.</title>\n</head>\n<body>\n<h1>Index of"
            b' /.</h1>\n<ul>\n<li><a href="/%3Cimg%20src=0%20onerror=alert(1)%3E.dir">&l'
            b't;img src=0 onerror=alert(1)&gt;.dir/</a></li>\n<li><a href="/%3Cimg%20sr'
            b'c=0%20onerror=alert(1)%3E.txt">&lt;img src=0 onerror=alert(1)&gt;.txt</a></l'
            b"i>\n</ul>\n</body>\n</html>",
        ),
        pytest.param(
            True,
            200,
            "/static",
            "/static",
            b"<html>\n<head>\n<title>Index of /.</title>\n</head>\n<body>\n<h1>Index of"
            b' /.</h1>\n<ul>\n<li><a href="/static/%3Cimg%20src=0%20onerror=alert(1)%3E.'
            b'dir">&lt;img src=0 onerror=alert(1)&gt;.dir/</a></li>\n<li><a href="/stat'
            b'ic/%3Cimg%20src=0%20onerror=alert(1)%3E.txt">&lt;img src=0 onerror=alert(1)&'
            b"gt;.txt</a></li>\n</ul>\n</body>\n</html>",
            id="index_static",
        ),
        pytest.param(
            True,
            200,
            "/static",
            "/static/<img src=0 onerror=alert(1)>.dir",
            b"<html>\n<head>\n<title>Index of /&lt;img src=0 onerror=alert(1)&gt;.dir</t"
            b"itle>\n</head>\n<body>\n<h1>Index of /&lt;img src=0 onerror=alert(1)&gt;.di"
            b'r</h1>\n<ul>\n<li><a href="/static/%3Cimg%20src=0%20onerror=alert(1)%3E.di'
            b'r/my_file_in_dir">my_file_in_dir</a></li>\n</ul>\n</body>\n</html>',
            id="index_subdir",
        ),
    ],
)
async def test_access_root_of_static_handler_xss(
    tmp_path,
    aiohttp_client,
    show_index,
    status,
    prefix,
    request_path,
    data,
) -> None:
    # Tests the operation of static file server.
    # Try to access the root of static file server, and make
    # sure that correct HTTP statuses are returned depending if we directory
    # index should be shown or not.
    # Ensure that html in file names is escaped.
    # Ensure that links are url quoted.
    my_file = tmp_path / "<img src=0 onerror=alert(1)>.txt"
    my_dir = tmp_path / "<img src=0 onerror=alert(1)>.dir"
    my_dir.mkdir()
    my_file_in_dir = my_dir / "my_file_in_dir"

    with my_file.open("w") as fw:
        fw.write("hello")

    with my_file_in_dir.open("w") as fw:
        fw.write("world")

    app = web.Application()

    # Register global static route:
    app.router.add_static(prefix, str(tmp_path), show_index=show_index)
    client = await aiohttp_client(app)

    # Request the root of the static directory.
    r = await client.get(request_path)
    assert r.status == status

    if data:
        assert r.headers["Content-Type"] == "text/html; charset=utf-8"
        read_ = await r.read()
        assert read_ == data


async def test_follow_symlink(
    tmp_dir_path: pathlib.Path, aiohttp_client: AiohttpClient
) -> None:
    # Tests the access to a symlink, in static folder
    data = "hello world"

    my_dir_path = os.path.join(tmp_dir_path, "my_dir")
    os.mkdir(my_dir_path)

    my_file_path = os.path.join(my_dir_path, "my_file_in_dir")
    with open(my_file_path, "w") as fw:
        fw.write(data)

    my_symlink_path = os.path.join(tmp_dir_path, "my_symlink")
    os.symlink(my_dir_path, my_symlink_path)

    app = web.Application()

    # Register global static route:
    app.router.add_static("/", tmp_dir_path, follow_symlinks=True)
    client = await aiohttp_client(app)

    # Request the root of the static directory.
    r = await client.get("/my_symlink/my_file_in_dir")
    assert r.status == 200
    assert (await r.text()) == data


async def test_follow_symlink_directory_traversal(
    tmp_path, aiohttp_client
) -> None:
    # Tests that follow_symlinks does not allow directory transversal
    data = "private"

    private_file = tmp_path / "private_file"
    private_file.write_text(data)

    safe_path = tmp_path / "safe_dir"
    safe_path.mkdir()

    app = web.Application()

    # Register global static route:
    app.router.add_static("/", str(safe_path), follow_symlinks=True)
    client = await aiohttp_client(app)

    await client.start_server()
    # We need to use a raw socket to test this, as the client will normalize
    # the path before sending it to the server.
    reader, writer = await asyncio.open_connection(client.host, client.port)
    writer.write(b"GET /../private_file HTTP/1.1\r\n\r\n")
    response = await reader.readuntil(b"\r\n\r\n")
    assert b"404 Not Found" in response
    writer.close()
    await client.close()


async def test_follow_symlink_directory_traversal_after_normalization(
    tmp_path, aiohttp_client
) -> None:
    # Tests that follow_symlinks does not allow directory transversal
    # after normalization
    #
    # Directory structure
    # |-- secret_dir
    # |   |-- private_file (should never be accessible)
    # |   |-- symlink_target_dir
    # |       |-- symlink_target_file (should be accessible via the my_symlink symlink)
    # |       |-- sandbox_dir
    # |           |-- my_symlink -> symlink_target_dir
    #
    secret_path = tmp_path / "secret_dir"
    secret_path.mkdir()

    # This file is below the symlink target and should not be reachable
    private_file = secret_path / "private_file"
    private_file.write_text("private")

    symlink_target_path = secret_path / "symlink_target_dir"
    symlink_target_path.mkdir()

    sandbox_path = symlink_target_path / "sandbox_dir"
    sandbox_path.mkdir()

    # This file should be reachable via the symlink
    symlink_target_file = symlink_target_path / "symlink_target_file"
    symlink_target_file.write_text("readable")

    my_symlink_path = sandbox_path / "my_symlink"
    pathlib.Path(str(my_symlink_path)).symlink_to(str(symlink_target_path), True)

    app = web.Application()

    # Register global static route:
    app.router.add_static("/", str(sandbox_path), follow_symlinks=True)
    client = await aiohttp_client(app)

    await client.start_server()
    # We need to use a raw socket to test this, as the client will normalize
    # the path before sending it to the server.
    reader, writer = await asyncio.open_connection(client.host, client.port)
    writer.write(b"GET /my_symlink/../private_file HTTP/1.1\r\n\r\n")
    response = await reader.readuntil(b"\r\n\r\n")
    assert b"404 Not Found" in response
    writer.close()

    reader, writer = await asyncio.open_connection(client.host, client.port)
    writer.write(b"GET /my_symlink/symlink_target_file HTTP/1.1\r\n\r\n")
    response = await reader.readuntil(b"\r\n\r\n")
    assert b"200 OK" in response
    response = await reader.readuntil(b"readable")
    assert response == b"readable"
    writer.close()
    await client.close()


@pytest.mark.parametrize(
    "dir_name,filename,data",
    [
        ("", "test file.txt", "test text"),
        ("test dir name", "test dir file .txt", "test text file folder"),
    ],
)
async def test_access_to_the_file_with_spaces(
    tmp_dir_path: pathlib.Path,
    aiohttp_client: AiohttpClient,
    dir_name: str,
    filename: str,
    data: str,
) -> None:
    # Checks operation of static files with spaces

    my_dir_path = os.path.join(tmp_dir_path, dir_name)

    if dir_name:
        os.mkdir(my_dir_path)

    my_file_path = os.path.join(my_dir_path, filename)

    with open(my_file_path, "w") as fw:
        fw.write(data)

    app = web.Application()

    url = os.path.join("/", dir_name, filename)

    app.router.add_static("/", tmp_dir_path)
    client = await aiohttp_client(app)

    r = await client.get(url)
    assert r.status == 200
    assert (await r.text()) == data
    await r.release()


async def test_access_non_existing_resource(
    tmp_dir_path: pathlib.Path, aiohttp_client: AiohttpClient
) -> None:
    # Tests accessing non-existing resource
    # Try to access a non-exiting resource and make sure that 404 HTTP status
    # returned.
    app = web.Application()

    # Register global static route:
    app.router.add_static("/", tmp_dir_path, show_index=True)
    client = await aiohttp_client(app)

    # Request the root of the static directory.
    r = await client.get("/non_existing_resource")
    assert r.status == 404


@pytest.mark.parametrize(
    "registered_path,request_url",
    [
        ("/a:b", "/a:b"),
        ("/a@b", "/a@b"),
        ("/a:b", "/a%3Ab"),
    ],
)
async def test_url_escaping(
    aiohttp_client: AiohttpClient, registered_path: str, request_url: str
) -> None:
    # Tests accessing a resource with
    app = web.Application()

    async def handler(request: web.Request) -> web.Response:
        return web.Response()

    app.router.add_get(registered_path, handler)
    client = await aiohttp_client(app)

    r = await client.get(request_url)
    assert r.status == 200


async def test_handler_metadata_persistence() -> None:
    """Tests accessing metadata of a handler after registering it on the app router."""
    app = web.Application()

    async def async_handler(request: web.Request) -> web.Response:
        """Doc"""
        return web.Response()

    def sync_handler(request):
        """Doc"""
        return web.Response()

    app.router.add_get("/async", async_handler)
    with pytest.warns(DeprecationWarning):
        app.router.add_get("/sync", sync_handler)

    for resource in app.router.resources():
        for route in resource:
            assert route.handler.__doc__ == "Doc"


async def test_unauthorized_folder_access(
    tmp_dir_path: pathlib.Path, aiohttp_client: AiohttpClient
) -> None:
    # Tests the unauthorized access to a folder of static file server.
    # Try to list a folder content of static file server when server does not
    # have permissions to do so for the folder.
    my_dir_path = os.path.join(tmp_dir_path, "my_dir")
    os.mkdir(my_dir_path)

    app = web.Application()

    with mock.patch("pathlib.Path.__new__") as path_constructor:
        path = MagicMock()
        path.joinpath.return_value = path
        path.resolve.return_value = path
        path.iterdir.return_value.__iter__.side_effect = PermissionError()
        path_constructor.return_value = path

        # Register global static route:
        app.router.add_static("/", tmp_dir_path, show_index=True)
        client = await aiohttp_client(app)

        # Request the root of the static directory.
        r = await client.get("/my_dir")
        assert r.status == 403


async def test_access_compressed_file_as_symlink(tmp_path, aiohttp_client) -> None:
    """Test that compressed file variants as symlinks are ignored."""
    private_file = tmp_path / "private.txt"
    private_file.write_text("private info")
    www_dir = tmp_path / "www"
    www_dir.mkdir()
    gz_link = www_dir / "file.txt.gz"
    gz_link.symlink_to(f"../{private_file.name}")

    app = web.Application()
    app.router.add_static("/", www_dir)
    client = await aiohttp_client(app)

    # Symlink should be ignored; response reflects missing uncompressed file.
    resp = await client.get(f"/{gz_link.stem}")
    assert resp.status == 404
    resp.release()

    # Again symlin is ignored, and then uncompressed is served.
    txt_file = gz_link.with_suffix("")
    txt_file.write_text("public data")
    resp = await client.get(f"/{txt_file.name}")
    assert resp.status == 200
    assert resp.headers.get("Content-Encoding") is None
    assert resp.content_type == "text/plain"
    assert await resp.text() == "public data"
    resp.release()
    await client.close()


async def test_access_symlink_loop(
    tmp_dir_path: pathlib.Path, aiohttp_client: AiohttpClient
) -> None:
    # Tests the access to a looped symlink, which could not be resolved.
    my_dir_path = os.path.join(tmp_dir_path, "my_symlink")
    os.symlink(my_dir_path, my_dir_path)

    app = web.Application()

    # Register global static route:
    app.router.add_static("/", tmp_dir_path, show_index=True)
    client = await aiohttp_client(app)

    # Request the root of the static directory.
    r = await client.get("/my_symlink")
    assert r.status == 404


async def test_access_special_resource(
    tmp_dir_path: pathlib.Path, aiohttp_client: AiohttpClient
) -> None:
    # Tests the access to a resource that is neither a file nor a directory.
    # Checks that if a special resource is accessed (f.e. named pipe or UNIX
    # domain socket) then 404 HTTP status returned.
    app = web.Application()

    with mock.patch("pathlib.Path.__new__") as path_constructor:
        special = MagicMock()
        special.is_dir.return_value = False
        special.is_file.return_value = False

        path = MagicMock()
        path.joinpath.side_effect = lambda p: (special if p == "special" else path)
        path.resolve.return_value = path
        special.resolve.return_value = special

        path_constructor.return_value = path

        # Register global static route:
        app.router.add_static("/", tmp_dir_path, show_index=True)
        client = await aiohttp_client(app)

        # Request the root of the static directory.
        r = await client.get("/special")
        assert r.status == 403


async def test_partially_applied_handler(aiohttp_client: AiohttpClient) -> None:
    app = web.Application()

    async def handler(data, request):
        return web.Response(body=data)

    app.router.add_route("GET", "/", functools.partial(handler, b"hello"))

    client = await aiohttp_client(app)

    r = await client.get("/")
    data = await r.read()
    assert data == b"hello"


async def test_static_head(
    tmp_path: pathlib.Path, aiohttp_client: AiohttpClient
) -> None:
    # Test HEAD on static route
    my_file_path = tmp_path / "test.txt"
    with my_file_path.open("wb") as fw:
        fw.write(b"should_not_see_this\n")

    app = web.Application()
    app.router.add_static("/", str(tmp_path))
    client = await aiohttp_client(app)

    r = await client.head("/test.txt")
    assert r.status == 200

    # Check that there is no content sent (see #4809). This can't easily be
    # done with aiohttp_client because the buffering can consume the content.
    reader, writer = await asyncio.open_connection(client.host, client.port)
    writer.write(b"HEAD /test.txt HTTP/1.1\r\n")
    writer.write(b"Host: localhost\r\n")
    writer.write(b"Connection: close\r\n")
    writer.write(b"\r\n")
    while await reader.readline() != b"\r\n":
        pass
    content = await reader.read()
    writer.close()
    assert content == b""


def test_system_route() -> None:
    route = SystemRoute(web.HTTPCreated(reason="test"))
    with pytest.raises(RuntimeError):
        route.url_for()
    assert route.name is None
    assert route.resource is None
    assert "<SystemRoute 201: test>" == repr(route)
    assert 201 == route.status
    assert "test" == route.reason


async def test_412_is_returned(aiohttp_client: AiohttpClient) -> None:
    class MyRouter(abc.AbstractRouter):
        async def resolve(self, request):
            raise web.HTTPPreconditionFailed()

    with pytest.warns(DeprecationWarning):
        app = web.Application(router=MyRouter())

    client = await aiohttp_client(app)

    resp = await client.get("/")

    assert resp.status == 412


async def test_allow_head(aiohttp_client: AiohttpClient) -> None:
    # Test allow_head on routes.
    app = web.Application()

    async def handler(request: web.Request) -> web.Response:
        return web.Response()

    app.router.add_get("/a", handler, name="a")
    app.router.add_get("/b", handler, allow_head=False, name="b")
    client = await aiohttp_client(app)

    r = await client.get("/a")
    assert r.status == 200
    await r.release()

    r = await client.head("/a")
    assert r.status == 200
    await r.release()

    r = await client.get("/b")
    assert r.status == 200
    await r.release()

    r = await client.head("/b")
    assert r.status == 405
    await r.release()


@pytest.mark.parametrize(
    "path",
    [
        "/a",
        "/{a}",
    ],
)
def test_reuse_last_added_resource(path: str) -> None:
    # Test that adding a route with the same name and path of the last added
    # resource doesn't create a new resource.
    app = web.Application()

    async def handler(request: web.Request) -> web.Response:
        return web.Response()

    app.router.add_get(path, handler, name="a")
    app.router.add_post(path, handler, name="a")

    assert len(app.router.resources()) == 1


def test_resource_raw_match() -> None:
    app = web.Application()

    async def handler(request: web.Request) -> web.Response:
        return web.Response()

    route = app.router.add_get("/a", handler, name="a")
    assert route.resource is not None
    assert route.resource.raw_match("/a")

    route = app.router.add_get("/{b}", handler, name="b")
    assert route.resource is not None
    assert route.resource.raw_match("/{b}")

    resource = app.router.add_static("/static", ".")
    assert not resource.raw_match("/static")


async def test_add_view(aiohttp_client: AiohttpClient) -> None:
    app = web.Application()

    class MyView(web.View):
        async def get(self) -> web.Response:
            return web.Response()

        async def post(self) -> web.Response:
            return web.Response()

    app.router.add_view("/a", MyView)

    client = await aiohttp_client(app)

    r = await client.get("/a")
    assert r.status == 200
    await r.release()

    r = await client.post("/a")
    assert r.status == 200
    await r.release()

    r = await client.put("/a")
    assert r.status == 405
    await r.release()


async def test_decorate_view(aiohttp_client: AiohttpClient) -> None:
    routes = web.RouteTableDef()

    @routes.view("/a")
    class MyView(web.View):
        async def get(self) -> web.Response:
            return web.Response()

        async def post(self) -> web.Response:
            return web.Response()

    app = web.Application()
    app.router.add_routes(routes)

    client = await aiohttp_client(app)

    r = await client.get("/a")
    assert r.status == 200
    await r.release()

    r = await client.post("/a")
    assert r.status == 200
    await r.release()

    r = await client.put("/a")
    assert r.status == 405
    await r.release()


async def test_web_view(aiohttp_client: AiohttpClient) -> None:
    app = web.Application()

    class MyView(web.View):
        async def get(self) -> web.Response:
            return web.Response()

        async def post(self) -> web.Response:
            return web.Response()

    app.router.add_routes([web.view("/a", MyView)])

    client = await aiohttp_client(app)

    r = await client.get("/a")
    assert r.status == 200
    await r.release()

    r = await client.post("/a")
    assert r.status == 200
    await r.release()

    r = await client.put("/a")
    assert r.status == 405
    await r.release()


async def test_static_absolute_url(
    aiohttp_client: AiohttpClient, tmpdir: pathlib.Path
) -> None:
    # requested url is an absolute name like
    # /static/\\machine_name\c$ or /static/D:\path
    # where the static dir is totally different
    app = web.Application()
    fname = tmpdir / "file.txt"
    fname.write_text("sample text", "ascii")
    here = pathlib.Path(__file__).parent
    app.router.add_static("/static", here)
    client = await aiohttp_client(app)
    resp = await client.get("/static/" + str(fname))
    assert resp.status == 403


async def test_for_issue_5250(
    aiohttp_client: AiohttpClient, tmp_dir_path: pathlib.Path
) -> None:
    app = web.Application()
    app.router.add_static("/foo", tmp_dir_path)

    async def get_foobar(request: web.Request) -> web.Response:
        return web.Response(body="success!")

    app.router.add_get("/foobar", get_foobar)

    client = await aiohttp_client(app)
    async with await client.get("/foobar") as resp:
        assert resp.status == 200
        assert (await resp.text()) == "success!"


@pytest.mark.xfail(
    raises=AssertionError,
    reason="Regression in v3.7: https://github.com/aio-libs/aiohttp/issues/5621",
)
@pytest.mark.parametrize(
    ("route_definition", "urlencoded_path", "expected_http_resp_status"),
    (
        ("/467,802,24834/hello", "/467%2C802%2C24834/hello", 200),
        ("/{user_ids:([0-9]+)(,([0-9]+))*}/hello", "/467%2C802%2C24834/hello", 200),
        ("/1%2C3/hello", "/1%2C3/hello", 404),
    ),
    ids=("urldecoded_route", "urldecoded_route_with_regex", "urlencoded_route"),
)
async def test_decoded_url_match(
    aiohttp_client: AiohttpClient,
    route_definition: str,
    urlencoded_path: str,
    expected_http_resp_status: int,
) -> None:
    app = web.Application()

    async def handler(request: web.Request) -> web.Response:
        return web.Response()

    app.router.add_get(route_definition, handler)
    client = await aiohttp_client(app)

    r = await client.get(yarl.URL(urlencoded_path, encoded=True))
    assert r.status == expected_http_resp_status
    await r.release()
